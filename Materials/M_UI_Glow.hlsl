// M_UI_Glow — мягкое свечение под шкалой M_UI_SegBar, ПОВТОРЯЕТ её форму: наклон (SkewTan),
// рост сегментов (Ramp) и горящую часть (целыми сегментами или плавно — Continuous).
// Кладётся ПОД шкалу в Overlay с Padding = -Pad: картинка шире шкалы на Pad со всех сторон.
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV         TexCoord[0]
//   Size       Vector: XY = размер картинки свечения, px = шкала + 2*Pad (скорость 450 x 44, нитро 328 x 42)
//   Pad        Scalar: ширина ореола, px (скорость 10, нитро 14)
//   Falloff    Scalar: крутизна затухания (3 — мягко, 6 — коротко)
//   Color      Vector: цвет; A = яркость ореола (скорость 0.55, нитро 0.75)
//   Fill       Scalar: 0..1 — то же значение, что Fill у шкалы
//   Segments   Scalar: как у шкалы (скорость 22, нитро 4)
//   Gap        Scalar: как у шкалы (4 / 2)
//   SkewTan    Scalar: как у шкалы (0.364)
//   Ramp       Scalar: как у шкалы (скорость 0.58, нитро 0)
//   Continuous Scalar: как у шкалы (скорость 0, нитро 1)
// Выход: RGB -> Final Color, A -> Opacity.

float2 sz = Size.xy;
float2 bar = max(sz - 2.0 * Pad, 1.0);
float bx = UV.x * sz.x - Pad;
float by = (sz.y - Pad) - UV.y * sz.y;
float x  = bx - by * SkewTan;
float usable = bar.x - bar.y * SkewTan;
float pitch  = (usable + Gap) / Segments;
float lit    = (Continuous > 0.5) ? usable * saturate(Fill)
                                  : max(round(saturate(Fill) * Segments) * pitch - Gap, 0.0);
float t  = saturate(x / max(usable, 1.0));
float h  = bar.y * (1.0 - Ramp * (1.0 - t));
float dx = max(max(-x, x - lit), 0.0);
float dy = max(max(by - h, -by), 0.0);
float d  = length(float2(dx, dy));
float a  = Color.a * exp(-d * Falloff / max(Pad, 1.0)) * step(0.5, lit);
return float4(Color.rgb, a);
