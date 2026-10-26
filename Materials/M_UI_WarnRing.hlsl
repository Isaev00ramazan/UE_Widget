// M_UI_WarnRing — обод сенсора ракет: тонкое кольцо и засечки через равные углы (первая — сверху).
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV         TexCoord[0]
//   Size       Scalar: сторона квадратного Image, px (640)
//   Radius     Scalar: радиус обода от центра, px (264 = 640/2 - 56: место под подписи времени)
//   RingW      Scalar: толщина обода, px (2)
//   TrackColor Vector: цвет обода (track), A = сила
//   TickCount  Scalar: число засечек (12 — через 30 градусов)
//   TickLen    Scalar: длина засечки поперёк обода, px (10, по центру обода)
//   TickW      Scalar: толщина засечки, px (2)
//   TickColor  Vector: цвет засечек (edge), A = сила
// Выход: RGB -> Final Color, A -> Opacity.

float2 p = (UV - 0.5) * Size;   // px от центра, y вниз
float  r = length(p);

float ring = saturate(RingW * 0.5 - abs(r - Radius) + 0.5);

float ang  = atan2(p.x, -p.y);                         // 0 сверху, по часовой
float stepA = 6.2831853 / max(TickCount, 1.0);
float da   = ang - stepA * round(ang / stepA);         // угол до ближайшей засечки
float tick = saturate(TickW * 0.5 - abs(da * r) + 0.5) * saturate(TickLen * 0.5 - abs(r - Radius) + 0.5);

float a1 = ring * TrackColor.a;
float a2 = tick * TickColor.a;
float alpha = a2 + a1 * (1.0 - a2);
float3 rgb = (TickColor.rgb * a2 + TrackColor.rgb * a1 * (1.0 - a2)) / max(alpha, 0.0001);
return float4(rgb, alpha);
