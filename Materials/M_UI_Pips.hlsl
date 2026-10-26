// M_UI_Pips — пипсы магазина: Count вертикальных пуль, общая заливка Fill делится между ними.
// Пипс i заполнен на saturate(Fill * Count - i): правый пустеет первым, частичный — сверху вниз
// (магазин 12, патронов 11 -> 5 полных + шестой наполовину; магазин 18, 17 -> шестой опустел на 33%).
// Пули фиксированного размера PipSize, Gap — только расстояние между ними: размер пуль от Gap и Size
// не зависит. Ряд прижат влево и по центру по высоте; лишнее место картинки прозрачное.
// Края сглаживаются по ЭКРАННЫМ пикселям (fwidth) — чёткие при любом масштабе (в превью материала
// старое сглаживание в «пикселях материала» растягивалось вместе с картинкой и мылило края).
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV         TexCoord[0]
//   Size       Vector: XY = размер картинки (Image Size в виджете), px. Ширина не меньше
//              Count * PipSize.x + (Count - 1) * Gap, высота не меньше PipSize.y
//   PipSize    Vector: XY = размер одной пули, px (4 x 16; маска 8 x 32 — та же пропорция 1:4)
//   Count      Scalar: число пипсов
//   Gap        Scalar: расстояние между пулями, px
//   Round      Scalar: радиус скругления углов, px (0 — при маске пули, форму даёт она)
//   Mask       Texture Object: форма пули в альфе (белая), растягивается на PipSize.
//              ⚠️ У текстуры Tiling X/Y = Clamp: при Wrap нижний ряд подмешивается к острию полоской.
//              Без текстуры (заглушка WhiteSquare) — прямоугольник со скруглением Round
//   Fill       Scalar: 0..1 (магазин CurrentAmmo / MagazineSize; при перезарядке — её прогресс)
//   OnColor    Vector: заполненная часть
//   OffColor   Vector: пустая часть (track)
//   EdgeColor  Vector: заполненная часть ЧАСТИЧНОГО пипса (жёлтый при перезарядке), A = 0 — как OnColor
// Выход: RGB -> Final Color, A -> Opacity.

float2 sz    = Size.xy;
float2 p     = UV * sz;
float2 ps    = max(PipSize.xy, 0.001);
float  pitch = ps.x + Gap;
float2 aa    = max(fwidth(p), 0.0001);         // один экранный пиксель в px материала

float  i  = floor(p.x / pitch);
float  fx = p.x - i * pitch;                   // px от левого края пули
float  ly = p.y - (sz.y - ps.y) * 0.5;         // px от верха пули

// Форма: прямоугольник пули (со скруглением Round) x маска; зазор и лишнее место — снаружи
float2 c  = float2(fx, ly) - ps * 0.5;
float  r  = min(Round, min(ps.x, ps.y) * 0.5);
float2 q  = abs(c) - ps * 0.5 + r;
float  d  = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
float  shape = saturate(0.5 - d / max(aa.x, aa.y));

float2 luv  = saturate(float2(fx, ly) / ps);
float  mask = Texture2DSample(Mask, MaskSampler, luv).a;
float  inPip = shape * mask * step(0.0, i) * step(i, Count - 1.0);

// Заливка снизу вверх, граница — тоже в экранных пикселях
float f   = saturate(Fill * Count - i);
float yb  = ps.y - ly;                         // px от низа пули
float lit = saturate((f * ps.y - yb) / aa.y + 0.5);

float partial = step(0.001, f) * step(f, 0.999) * step(0.001, EdgeColor.a);
float4 onC = lerp(OnColor, EdgeColor, partial);
float4 col = lerp(OffColor, onC, lit);
return float4(col.rgb, col.a * inPip);
