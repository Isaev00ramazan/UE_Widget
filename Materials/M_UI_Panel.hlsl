// M_UI_Panel — стеклянная панель со скосами.
// Custom node, Output Type = CMOT Float 4. Входы (имена важны):
//   UV        TexCoord[0]
//   Size      Vector: XY = размер виджета в px сетки 1080p (например 344, 62)
//   Cut       Scalar: длина катета скоса, px (12 панели, 7 мелочь)
//   Corners   Vector: 1/0 для углов (R = верх-лево, G = верх-право, B = низ-право, A = низ-лево)
//   Circle    Vector: XY = центр выреза в px от верх-левого угла панели, Z = радиус выреза (0 = без выреза)
//   Fill      Vector: цвет заливки (glass), A = непрозрачность
//   HeadH     Scalar: высота полосы заголовка, px (0 = нет)
//   HeadColor Vector: цвет полосы заголовка (glass-head), A = сила
//   Edge      Vector: цвет блика по верхнему краю (edge), A = сила
//   Zone      Vector: цвет засечки зоны (race / combat), A = 1 вкл / 0 выкл
//   StrokeW   Scalar: толщина рамки по контуру (со скосами), px
//   StrokeColor Vector: цвет рамки, A = 0 — рамки нет (HULL CRITICAL: красная)
//             Рамка — в самом материале: отдельная плашка под полупрозрачной панелью просвечивала бы целиком
//   InnerGlowPx    Scalar: внутреннее свечение от контура внутрь, px (дебафф при попадании: 14)
//   InnerGlowColor Vector: его цвет, A = сила; 0 — нет
// Выход: RGB -> Final Color, A -> Opacity (Material Domain = User Interface, Blend Mode = Translucent).

float2 sz = Size.xy;
float2 p  = UV * sz;          // px от верх-левого угла
float2 q  = sz - p;           // px от низ-правого угла
const float k = 0.70710678;   // 1/sqrt(2): расстояние до диагонали скоса

float a = 1.0;
if (Corners.r > 0.5) a = min(a, saturate((p.x + p.y - Cut) * k + 0.5));
if (Corners.g > 0.5) a = min(a, saturate((q.x + p.y - Cut) * k + 0.5));
if (Corners.b > 0.5) a = min(a, saturate((q.x + q.y - Cut) * k + 0.5));
if (Corners.a > 0.5) a = min(a, saturate((p.x + q.y - Cut) * k + 0.5));
if (Circle.z > 0.0)  a = min(a, saturate(length(p - Circle.xy) - Circle.z + 0.5));

float3 col = Fill.rgb;
float  op  = Fill.a;

// полоса заголовка
if (HeadH > 0.0) col = lerp(col, HeadColor.rgb, HeadColor.a * saturate(HeadH - p.y + 0.5));

// блик 1 px по верхнему краю
col = lerp(col, Edge.rgb, Edge.a * saturate(1.0 - p.y));

// засечка зоны 32 x 3 px сразу после скоса
float zx = Cut + 2.0;
float tick = step(zx, p.x) * step(p.x, zx + 32.0) * step(p.y, 3.0) * Zone.a;
col = lerp(col, Zone.rgb, tick);
op  = lerp(op, 1.0, tick);

// рамка: расстояние до ближайшего края контура (стороны, скосы, вырез)
float edgeD = min(min(p.x, p.y), min(q.x, q.y));
if (Corners.r > 0.5) edgeD = min(edgeD, (p.x + p.y - Cut) * k);
if (Corners.g > 0.5) edgeD = min(edgeD, (q.x + p.y - Cut) * k);
if (Corners.b > 0.5) edgeD = min(edgeD, (q.x + q.y - Cut) * k);
if (Corners.a > 0.5) edgeD = min(edgeD, (p.x + q.y - Cut) * k);
if (Circle.z > 0.0)  edgeD = min(edgeD, length(p - Circle.xy) - Circle.z);
// внутреннее свечение (CSS inset 0 0 Npx): гаснет от края внутрь, рамка рисуется поверх
float iglow = saturate(InnerGlowColor.a * exp(-max(edgeD, 0.0) * 2.0 / max(InnerGlowPx, 0.001))) * step(0.001, InnerGlowPx);
col = lerp(col, InnerGlowColor.rgb, iglow);
op  = op + (1.0 - op) * iglow;

float stroke = saturate(StrokeW - edgeD + 0.5) * StrokeColor.a;
col = lerp(col, StrokeColor.rgb, stroke);
op  = lerp(op, 1.0, stroke);

return float4(col, op * a);
