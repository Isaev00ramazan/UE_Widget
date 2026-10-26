// M_UI_WarnArc — дуга угрозы сенсора ракет: отрезок обода с центром СВЕРХУ, шеврон внутрь и свечение.
// Направление на ракету задаёт виджет поворотом Image (Render Transform Angle), не материал.
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV       TexCoord[0]
//   Size     Scalar: сторона квадратного Image, px (640, как у M_UI_WarnRing)
//   Radius   Scalar: радиус обода, px (264)
//   ArcDeg   Scalar: длина дуги, градусы (18 далеко / 26 близко / 34 вот-вот)
//   Width    Scalar: толщина дуги, px (6 / 8 / 10), концы прямые
//   ChevW    Scalar: ширина основания шеврона, px (18)
//   ChevH    Scalar: высота шеврона, px (12); основание в 4 px от внутреннего края дуги, острие к центру
//   GlowPx   Scalar: радиус свечения, px (8 — CSS drop-shadow 0 0 8px); 0 — без свечения
//   Color    Vector: цвет уровня (combat / hp), A = сила
//   Opacity  Scalar: общая прозрачность 0..1 — пульс и мигание крутит виджет
// Выход: RGB -> Final Color, A -> Opacity.

float2 p = (UV - 0.5) * Size;   // px от центра, y вниз
float  r = length(p);

// дуга: внутри по углу и внутри по толщине (оба — в px, для сглаживания края)
float angDeg  = degrees(atan2(p.x, -p.y));             // 0 сверху, -180..180
float angIn   = (ArcDeg * 0.5 - abs(angDeg)) * 0.0174533 * Radius;
float radIn   = Width * 0.5 - abs(r - Radius);
float arcD    = min(angIn, radIn);                     // > 0 внутри дуги
float arc     = saturate(arcD + 0.5);

// шеврон: d — px от внутреннего края дуги к центру по вертикальной оси
float d     = (Radius - Width * 0.5) + p.y;
float t     = (d - 4.0) / max(ChevH, 0.001);           // 0 у основания, 1 у острия
float halfW = ChevW * 0.5 * (1.0 - t);
float slope = ChevH / sqrt(ChevH * ChevH + ChevW * ChevW * 0.25);
float chevD = min(d - 4.0, (halfW - abs(p.x)) * slope);
float chev  = saturate(chevD + 0.5);

float shape = max(arc, chev);

// свечение вокруг дуги и шеврона, под ними
float outD  = max(-max(arcD, chevD), 0.0);
float glow  = (GlowPx > 0.0) ? exp(-outD * 2.0 / GlowPx) * 0.6 * (1.0 - shape) : 0.0;

float alpha = saturate(shape + glow) * Color.a * Opacity;
return float4(Color.rgb, alpha);
