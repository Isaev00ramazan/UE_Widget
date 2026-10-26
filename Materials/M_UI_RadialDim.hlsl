// M_UI_RadialDim — эллиптическое затемнение (CSS radial-gradient(RX% RY% at CX% CY%, Inner, Outer)).
// Фон экрана результатов: Center (0.40, 0.45), Radius (1.2, 0.9), Inner (6,18,22 @ .42), Outer (4,12,15 @ .86).
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV      TexCoord[0]
//   Center  Vector: XY — центр эллипса в долях картинки
//   Radius  Vector: XY — радиусы эллипса в долях ширины и высоты картинки
//   Inner   Vector: цвет в центре (A — прозрачность)
//   Outer   Vector: цвет на краю эллипса и дальше
// Выход: RGB -> Final Color, A -> Opacity.

float2 d = (UV - Center.xy) / max(Radius.xy, 0.0001);
return lerp(Inner, Outer, saturate(length(d)));
