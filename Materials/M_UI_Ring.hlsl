// M_UI_Ring — кольцо перезарядки навыка (заполняется по часовой стрелке от 12 часов).
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV         TexCoord[0]
//   Size       Scalar: сторона квадратного виджета, px (диск 96 + кольцо: ставьте Image 110 x 110)
//   RingW      Scalar: толщина кольца, px (4)
//   Pad        Scalar: отступ кольца от края виджета под свечение, px (0..8)
//   Progress   Scalar: 0..1
//   FillColor  Vector: combat (готов), ink-muted (перезарядка), race (активен)
//   TrackColor Vector: track
//   GlowColor  Vector: цвет свечения, A = сила (0 = без свечения); светится только при Progress = 1
// Выход: RGB -> Final Color, A -> Opacity.

float2 p = (UV - 0.5) * Size;   // px от центра, y вниз
float  r = length(p);
float  R = Size * 0.5 - Pad;

float ring = saturate(R - r + 0.5) * saturate(r - (R - RingW) + 0.5);

float t = frac(atan2(p.x, -p.y) / 6.2831853 + 1.0);   // 0 сверху, растёт по часовой
float edgePx = (Progress - t) * 6.2831853 * (R - RingW * 0.5);
float on = (Progress >= 0.9999) ? 1.0 : saturate(edgePx + 0.5) * step(0.0001, Progress);

float4 c = lerp(TrackColor, FillColor, on);
float alpha = c.a * ring;
float3 rgb = c.rgb;

if (GlowColor.a > 0.0 && Progress >= 0.9999 && Pad > 0.0)
{
    float halo = pow(saturate(1.0 - abs(r - (R - RingW * 0.5)) / (Pad + RingW)), 2.0) * GlowColor.a * (1.0 - ring);
    rgb = lerp(rgb, GlowColor.rgb, halo / max(alpha + halo, 0.0001));
    alpha = max(alpha, halo);
}
return float4(rgb, alpha);
