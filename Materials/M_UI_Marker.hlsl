// M_UI_Marker — метка радара целиком: заливка + обводка (по центру контура, как stroke в SVG) + свечение.
// Форма по Shape: 0 = круг (соперник), 1 = ромб (пикап), 2 = стрелка игрока (контур из системы:
// M160 140 L174 174 L160 166 L146 174 Z — центр картинки = центр габарита стрелки).
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV           TexCoord[0]
//   Size         Scalar: сторона картинки, px (с запасом под обводку и свечение)
//   Shape        Scalar: 0 круг, 1 ромб, 2 стрелка
//   Radius       Scalar: круг — радиус; ромб — половина диагонали; стрелка — половина высоты; px
//   FillColor    Vector: цвет заливки
//   OutlineColor Vector: цвет обводки (#06161A)
//   OutlineW     Scalar: толщина обводки, px (0 = без обводки)
//   GlowColor    Vector: цвет свечения, A = яркость (0 = без свечения)
//   GlowPx       Scalar: радиус свечения, px
// Выход: RGB -> Final Color, A -> Opacity.

float2 p = (UV - 0.5) * Size;
float d;
if (Shape < 0.5)
{
    d = length(p) - Radius;
}
else if (Shape < 1.5)
{
    d = (abs(p.x) + abs(p.y) - Radius) * 0.70710678;
}
else
{
    float sc = Radius / 17.0;
    float2 v0 = float2(0.0, -17.0) * sc;
    float2 v1 = float2(14.0, 17.0) * sc;
    float2 v2 = float2(0.0, 9.0) * sc;
    float2 v3 = float2(-14.0, 17.0) * sc;
    float2 vs[4] = { v0, v1, v2, v3 };
    float dd = dot(p - v0, p - v0);
    float sg = 1.0;
    for (int i = 0; i < 4; i++)
    {
        int j = (i + 3) % 4;
        float2 e = vs[j] - vs[i];
        float2 w = p - vs[i];
        float2 b = w - e * saturate(dot(w, e) / dot(e, e));
        dd = min(dd, dot(b, b));
        bool c1 = p.y >= vs[i].y;
        bool c2 = p.y < vs[j].y;
        bool c3 = e.x * w.y > e.y * w.x;
        if ((c1 && c2 && c3) || (!c1 && !c2 && !c3)) sg = -sg;
    }
    d = sg * sqrt(dd);
}

float hw     = OutlineW * 0.5;
float shapeA = saturate(hw - d + 0.5);
float fillA  = saturate(-hw - d + 0.5);
float mixF   = fillA / max(shapeA, 0.0001);
float3 sc3   = lerp(OutlineColor.rgb, FillColor.rgb, mixF);
float  sa    = shapeA * lerp(OutlineColor.a, FillColor.a, mixF);

float ga = GlowColor.a * exp(-max(d - hw, 0.0) * 3.0 / max(GlowPx, 0.001)) * step(0.001, GlowPx);
float a  = sa + ga * (1.0 - sa);
float3 col = (sc3 * sa + GlowColor.rgb * ga * (1.0 - sa)) / max(a, 0.0001);
return float4(col, a);
