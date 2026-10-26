// M_UI_Chevron — плашка-шеврон подбора: параллелограмм с наклоном −20° («/»), обводка по скошенным бокам,
// бегущие вправо полосы. Доска «Баннер подбора», вариант 3 (CSS: skewX(-20deg), inset 4px боков, полосы 12/24 px).
// Custom node, Output Type = CMOT Float 4. Входы (имена важны):
//   UV          TexCoord[0]
//   Size        Vector: XY = фактический размер Image, px (пишет код UPickupBannerWidget каждый кадр)
//   SkewTan     Scalar: тангенс наклона (tan 20° = 0.364); верх сдвинут вправо на SkewTan·высоту
//   Color       Vector: цвет обводки, заливки и полос (A не используется)
//   FillAlpha   Scalar: заливка (0.16)
//   BorderW     Scalar: толщина обводки боков, px по горизонтали (4)
//   StripeAlpha Scalar: полосы поверх заливки (0.10)
//   StripePeriod Scalar: шаг полос, px (24: 12 полоса + 12 зазор)
//   StripeSpeed Scalar: полосы бегут вправо, px/с (80)
//   Time        Time
// Выход: RGB -> Final Color, A -> Opacity (Material Domain = User Interface, Blend Mode = Translucent).

float2 sz = Size.xy;
float2 p  = UV * sz;                    // px от верх-левого угла Image
float xl = SkewTan * (sz.y - p.y);      // левый бок: внизу у края, вверху сдвинут вправо
float xr = sz.x - SkewTan * p.y;        // правый бок: вверху у края, внизу сдвинут влево
float inside = saturate(p.x - xl + 0.5) * saturate(xr - p.x + 0.5);

float u = p.x - xl;                     // px от левого бока вдоль строки — полосы параллельны бокам
float w = xr - xl;

// полосы: на первой половине шага, со сглаженными краями
float fs = frac((u - StripeSpeed * Time) / StripePeriod);
float sd = abs(fs - 0.25) * StripePeriod;
float stripe = saturate(StripePeriod * 0.25 - sd + 0.5) * StripeAlpha;

float border = max(saturate(BorderW - u + 0.5), saturate(BorderW - (w - u) + 0.5));

float op = FillAlpha + (1.0 - FillAlpha) * stripe;
op = lerp(op, 1.0, border);

return float4(Color.rgb, op * inside);
