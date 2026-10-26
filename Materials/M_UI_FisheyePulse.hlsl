// M_UI_FisheyePulse — (после v1) Effect Material для Retainer Box: вспышка рыбьего глаза на нитро.
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV        TexCoord[0]
//   Tex       Texture Object Parameter с именем "Texture" (Retainer Box подставляет в него HUD)
//   Screen    Vector: XY = размер экрана в px (1920, 1080 — достаточно сетки)
//   K         Scalar: сила; во время вспышки анимируйте 0 -> 0.035 -> 0 за 420 мс
//   Exponent  Scalar: 1
//   CenterY   Scalar: смещение центра линзы по вертикали, px (0)
// Выход: RGB -> Final Color, A -> Opacity.

float2 c = float2(0.5, 0.5 + CenterY / Screen.y);
float2 d = (UV - c) * Screen.xy / 960.0;
float r2 = dot(d, d);
float2 src = c + (UV - c) * (1.0 + K * pow(r2, Exponent));
float ok = step(0.0, src.x) * step(src.x, 1.0) * step(0.0, src.y) * step(src.y, 1.0);
return Texture2DSample(Tex, TexSampler, src) * ok;
