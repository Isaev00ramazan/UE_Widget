// M_UI_TextGlow — Effect Material для Retainer Box: свечение ПО ФОРМЕ содержимого (CSS text-shadow 0 0 Npx).
// Место на экране результатов: Radius 40, GlowColor player @ .35. «1» первой строки: Radius 16, combat @ .5.
// Retainer Box оборачивает текст с запасом под свечение (Padding = Radius со всех сторон) — иначе
// свечение обрежется краем render target.
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV         TexCoord[0]
//   Tex        Texture Object Parameter с именем "Texture" (Retainer Box подставляет содержимое)
//   Size       Vector: XY — размер Retainer Box, px
//   Radius     Scalar: радиус свечения, px (как blur в CSS)
//   GlowColor  Vector: цвет, A — яркость
// Выход: RGB -> Final Color, A -> Opacity.

float4 src = Texture2DSample(Tex, TexSampler, UV);

// Размытая альфа содержимого: 64 отсчёта по спирали (золотой угол), вес — гаусс (σ ≈ Radius/2, как в CSS)
float acc = 0.0;
float wsum = 0.0;
for (int i = 0; i < 64; i++)
{
    float r = sqrt((i + 0.5) / 64.0);
    float a = i * 2.39996323;
    float2 o = float2(cos(a), sin(a)) * r * Radius / max(Size.xy, 1.0);
    float w = exp(-r * r * 2.0);
    acc  += Texture2DSample(Tex, TexSampler, UV + o).a * w;
    wsum += w;
}
float g = saturate(acc / max(wsum, 0.0001)) * GlowColor.a;

// Текст поверх свечения
float  outA = src.a + g * (1.0 - src.a);
float3 outC = (src.rgb * src.a + GlowColor.rgb * g * (1.0 - src.a)) / max(outA, 0.0001);
return float4(outC, outA);
