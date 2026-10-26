// M_UI_SegBar — наклонные сегменты: скорость (22, растущие), HULL (20), нитро (4, сплошная), круги (3).
// Со встроенным свечением (GlowPad > 0): ореол повторяет форму шкалы и светит только под горящей частью.
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV         TexCoord[0]
//   Size       Vector: XY = размер САМОЙ ШКАЛЫ, px (скорость 430 x 24, HULL 304 x 9, нитро 300 x 14, круги 74 x 6)
//   Segments   Scalar: число сегментов
//   Gap        Scalar: зазор между сегментами, px
//   SkewTan    Scalar: tan(20 deg) = 0.364  (верх сегмента сдвинут вправо)
//   Fill       Scalar: 0..1
//   Ramp       Scalar: 0 = все одной высоты; 0.58 = первый сегмент 42% высоты (скорость)
//   Continuous Scalar: 1 = заливка плавная внутри сегмента, 0 = целыми сегментами
//   OnColor    Vector: горящие сегменты
//   OffColor   Vector: пустые (track)
//   PeakColor  Vector: последний горящий сегмент (скорость), A = 0 чтобы выключить
//   GlowPad    Scalar: ширина ореола, px. 0 = свечения нет, картинка = шкала (как раньше).
//                      > 0: Image в виджете кладётся с Padding = -GlowPad (картинка шире шкалы на GlowPad с каждой стороны)
//   GlowColor  Vector: цвет свечения, A = яркость (скорость race @ 0.55, нитро nitro @ 0.75)
//   GlowFalloff Scalar: крутизна затухания (3)
//   Trail      Scalar: след урона 0..1 (>= Fill): сегменты между Fill и Trail — цветом TrailColor. 0 — нет следа
//   TrailColor Vector: цвет следа (HULL: светлый), A = 0 — след выключен
//   OnColorEnd Vector: градиент горящих сегментов от OnColor (слева) к OnColorEnd (справа), A = 0 — без градиента
//   OffStroke  Vector: обводка ПУСТЫХ сегментов внутрь (пипсы стаков дебаффа), A = сила; 0 — нет
//   OffStrokeW Scalar: её толщина, px (1)
//   GainFrom   Scalar: восполнение (HP, нитро) — доля, С КОТОРОЙ выросла шкала; горящее от GainFrom до Fill —
//                      цветом GainColor. < 0 — выкл. Ведёт код виджета (UHUDHullWidget), не MVVM
//   GainColor  Vector: цвет новой части (HULL: зелёный хилки), A = сила — код гасит её к 0 («остывание»)
//   GainHeadColor Vector: яркий край горящей части 3 px, пока шкала растёт; A = сила, 0 — нет
//   GapFlash   Vector: вспышка делений между сегментами: x/y/z/w — 1-е…4-е деление, 0..1 (нитро: 25/50/75 %)
//   GapFlashColor Vector: её цвет (белый). Рисуется и за пределами шкалы — нужен GlowPad > 0
// Выход: RGB -> Final Color, A -> Opacity.

float2 sz   = Size.xy;
float2 full = sz + 2.0 * GlowPad;
float2 p    = UV * full - GlowPad;            // px внутри шкалы (может выходить за неё на GlowPad)
float  y    = sz.y - p.y;                     // px от низа шкалы
float  x    = p.x - y * SkewTan;              // снимаем наклон
float usable = sz.x - sz.y * SkewTan;
float pitch  = (usable + Gap) / Segments;
float segW   = pitch - Gap;

float i  = floor(x / pitch);
float fx = x - i * pitch;
float inSeg = step(0.0, i) * step(i, Segments - 1.0) * saturate(segW - fx + 0.5) * saturate(fx + 0.5);

float h   = sz.y * (1.0 - Ramp * (1.0 - i / max(Segments - 1.0, 1.0)));
float inH = saturate(h - y + 0.5) * saturate(y + 0.5);

float filled = Fill * Segments;
float lit = (Continuous > 0.5) ? saturate(saturate(filled - i) * segW - fx + 0.5)
                               : step(i + 1.0, round(filled));
float peak = PeakColor.a * step(round(filled) - 1.0, i) * step(i, round(filled) - 1.0) * (1.0 - step(0.5, Continuous));

// След урона: только там, где сегмент уже не горит
float trailF = max(Trail, Fill) * Segments;
float trail  = (Continuous > 0.5) ? saturate(saturate(trailF - i) * segW - fx + 0.5)
                                  : step(i + 1.0, round(trailF));
trail = saturate(trail - lit) * step(0.001, TrailColor.a);

// Градиент по шкале — по центру сегмента, чтобы сегмент был одного цвета
float  gt  = saturate((i + 0.5) / max(Segments, 1.0)) * step(0.001, OnColorEnd.a);
float4 onC = lerp(OnColor, OnColorEnd, gt);

float4 c = lerp(OffColor, onC, lit);
c = lerp(c, TrailColor, trail);

// Край горящей части: x, на котором кончается заливка (тот же, что у свечения ниже)
float litW = (Continuous > 0.5) ? usable * saturate(Fill)
                                : max(round(saturate(Fill) * Segments) * pitch - Gap, 0.0);

// Восполнение: горящее правее GainFrom — цветом GainColor; край заливки — GainHeadColor
float gainX = (Continuous > 0.5) ? usable * saturate(GainFrom) : round(saturate(GainFrom) * Segments) * pitch;
float gain  = lit * saturate(x - gainX + 0.5) * step(0.0, GainFrom) * GainColor.a;
c.rgb = lerp(c.rgb, GainColor.rgb, gain);
float head = lit * saturate(3.0 - (litW - x) + 0.5) * GainHeadColor.a;
c.rgb = lerp(c.rgb, GainHeadColor.rgb, head);

// Обводка пустого сегмента: расстояние до его краёв (наклон уже снят в x)
float edgeIn = min(min(fx, segW - fx), min(y, h - y));
float offEdge = saturate(OffStrokeW - edgeIn + 0.5) * OffStroke.a * (1.0 - lit) * (1.0 - trail);
c.rgb = lerp(c.rgb, OffStroke.rgb, offEdge);
c.a   = max(c.a, offEdge);
c.rgb = lerp(c.rgb, PeakColor.rgb, peak);
c.a   = lerp(c.a, 1.0, peak);
float barA = c.a * inSeg * inH;

// Свечение: расстояние до горящей части шкалы (наклон и рост сегментов учтены)
float t  = saturate(x / max(usable, 1.0));
float hg = sz.y * (1.0 - Ramp * (1.0 - t));
float dx = max(max(-x, x - litW), 0.0);
float dy = max(max(y - hg, -y), 0.0);
float d  = length(float2(dx, dy));
float glowA = GlowColor.a * exp(-d * GlowFalloff / max(GlowPad, 1.0)) * step(0.5, litW) * step(0.001, GlowPad);

float a = barA + glowA * (1.0 - barA);
float3 col = (c.rgb * barA + GlowColor.rgb * glowA * (1.0 - barA)) / max(a, 0.0001);

// Вспышка делений: полоска 3 px по зазору, на 3 px выше и ниже шкалы, с ореолом 4 px — поверх всего
float4 gf = GapFlash;
float flash = 0.0;
for (int k = 0; k < 4; k++)
{
    float amount = (k == 0) ? gf.x : ((k == 1) ? gf.y : ((k == 2) ? gf.z : gf.w));
    float gc  = (k + 1.0) * pitch - Gap * 0.5;
    float dg  = max(abs(x - gc) - 1.5, max(-y - 3.0, y - (sz.y + 3.0)));
    float fk  = max(saturate(0.5 - dg), 0.8 * exp(-max(dg, 0.0) / 4.0));
    flash = max(flash, amount * fk * step(k + 2.0, Segments));
}
col = lerp(col, GapFlashColor.rgb, saturate(flash / max(a + flash, 0.0001)));
a   = max(a, flash);
return float4(col, a);
