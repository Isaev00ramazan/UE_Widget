// M_UI_Gradient — горизонтальный градиент на 4 точки (CSS linear-gradient(90deg, …)).
// Строка игрока в результатах: C0 .30 → (P1 .55) C1 .10 → C2/C3 .03 (P2 = 1).
// Подвал результатов: C0 α0 → (P1 .12) C1 .6 → (P2 .88) C2 .6 → C3 α0.
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV  TexCoord[0]
//   C0  Vector: цвет у левого края (A — прозрачность)
//   P1  Scalar: где C1, доля ширины 0..1
//   C1  Vector
//   P2  Scalar: где C2, доля ширины 0..1 (>= P1)
//   C2  Vector
//   C3  Vector: цвет у правого края
// Выход: RGB -> Final Color, A -> Opacity.

float x  = saturate(UV.x);
float p1 = saturate(P1);
float p2 = max(saturate(P2), p1);
float4 c;
if (x < p1)      c = lerp(C0, C1, x / max(p1, 0.0001));
else if (x < p2) c = lerp(C1, C2, (x - p1) / max(p2 - p1, 0.0001));
else             c = lerp(C2, C3, (x - p2) / max(1.0 - p2, 0.0001));
return c;
