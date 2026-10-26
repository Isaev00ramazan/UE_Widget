// M_UI_RadialGlow — круглое мягкое свечение (стрелка игрока на радаре, glow-player).
// Image кладётся ПОД иконку, по центру.
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV      TexCoord[0]
//   Size    Scalar: сторона картинки, px (стрелка 20x25 -> 44)
//   Core    Scalar: радиус ровной части, px (6) — дальше затухание до края картинки
//   Color   Vector: цвет; A = яркость (player @ 0.8)
// Выход: RGB -> Final Color, A -> Opacity.

float2 p = (UV - 0.5) * Size;
float  r = length(p);
float  t = saturate((r - Core) / max(Size * 0.5 - Core, 1.0));
float  a = Color.a * (1.0 - t) * (1.0 - t);
return float4(Color.rgb, a);
