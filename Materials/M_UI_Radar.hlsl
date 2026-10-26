// M_UI_Radar — радар по дизайн-системе (Claude Design, HudScreen/RaceStandings): фон с радиальным
// градиентом и тёмной виньеткой по краю, карта трассы, 3 кольца, перекрестие, черточки каждые 15°
// (длинные каждые 45°), луч, снаружи круга — светлый кант 1.5 px, тёмный обод 8 px, тонкий светлый 1 px.
// Геометрия — в единицах SVG системы (радиус = 160), пересчитывается в px через RadarR.
// Картинка БОЛЬШЕ круга на 9 px с каждой стороны (под внешний обод): Size = 2*RadarR + 18 = 250,
// в виджете Image кладётся с Padding = -9.
// Custom node, Output Type = CMOT Float 4. Входы:
//   UV          TexCoord[0]
//   Size        Scalar: сторона картинки, px (250)
//   RadarR      Scalar: радиус круга радара, px (116)
//   Map         Texture Object: вид сверху на трассу, трасса = белая в альфе
//   Player      Vector: XY = позиция игрока в UV карты (0..1)
//   Yaw         Scalar: курс игрока, радианы, по часовой от «верха» карты
//   Zoom        Scalar: сколько UV карты помещается в радиус радара (0.12)
//   Time        Time node
//   SweepPeriod Scalar: секунд на оборот луча (5)
//   BgCenter    Vector: фон в центре (18,46,52 @ 0.78)
//   BgEdge      Vector: фон у края (8,22,27 @ 0.90)
//   TrackColor  Vector: полоса трассы (150,210,210 @ 0.26)
//   LineColor   Vector: кольца, перекрестие, внутренний кант (edge: 190,235,235 @ 0.20)
//   LineW       Scalar: толщина колец и перекрестия, px (0.75)
//   TickColor   Vector: черточки (ink-muted @ 0.55)
//   TickW       Scalar: толщина черточек, px (1.45)
//   SweepColor  Vector: луч (race @ 0.22)
//   BezelColor  Vector: тёмный обод (8,22,27 @ 0.72)
//   OuterAlpha  Scalar: альфа внешнего светлого 1 px (0.12)
// Выход: RGB -> Final Color, A -> Opacity. Метки и стрелку игрока — отдельными Image поверх.

float2 px = (UV - 0.5) * Size;
float  r  = length(px);
float  k  = RadarR / 160.0;
float  inside = saturate(RadarR - r + 0.5);

float  g  = saturate(r / (0.7 * RadarR * 1.41421356));
float4 bg = lerp(BgCenter, BgEdge, g);

float  sn = sin(Yaw), cs = cos(Yaw);
float2 nn = px / RadarR;
float2 rp = float2(nn.x * cs - nn.y * sn, nn.x * sn + nn.y * cs);
float  map = Texture2DSample(Map, MapSampler, Player.xy + rp * Zoom).a;
float3 col = lerp(bg.rgb, TrackColor.rgb, map * TrackColor.a);

float lw = LineW * 0.5;
float lines = saturate(lw - abs(r - 56.0 * k) + 0.5);
lines = max(lines, saturate(lw - abs(r - 106.0 * k) + 0.5));
lines = max(lines, saturate(lw - abs(r - 152.0 * k) + 0.5));
lines = max(lines, saturate(lw - min(abs(px.x), abs(px.y)) + 0.5) * saturate(152.0 * k - r + 0.5));
col = lerp(col, LineColor.rgb, lines * LineColor.a);

float ang  = atan2(px.x, -px.y);
float st   = 0.26179939;
float ai   = round(ang / st);
float da   = ang - ai * st;
float perp = abs(r * sin(da));
float major = step(fmod(abs(ai), 3.0), 0.01);
float r1   = lerp(150.0, 144.0, major) * k;
float along = saturate(r - r1 + 0.5) * saturate(157.0 * k - r + 0.5) * step(0.0, cos(da));
float tick = saturate(TickW * 0.5 - perp + 0.5) * along;
col = lerp(col, TickColor.rgb, tick * TickColor.a);

float a01   = frac(ang / 6.2831853 + 1.0);
float head  = frac(Time / SweepPeriod);
float ahead = frac(a01 - head + 1.0);
col = lerp(col, SweepColor.rgb, saturate(1.0 - ahead / 0.19444) * SweepColor.a);

float vig = 0.5 * pow(saturate(1.0 - (RadarR - r) / 44.0), 2.0);
col *= 1.0 - vig;
float aIn = inside * bg.a;

float ab = saturate(r - RadarR + 0.5) * saturate(RadarR + 8.0 - r + 0.5) * BezelColor.a;
float ae = saturate(r - RadarR + 0.5) * saturate(RadarR + 1.5 - r + 0.5) * LineColor.a;
float ao = saturate(r - (RadarR + 8.0) + 0.5) * saturate(RadarR + 9.0 - r + 0.5) * OuterAlpha;
float aOut = ae + ab * (1.0 - ae);
float3 cOut = (LineColor.rgb * ae + BezelColor.rgb * ab * (1.0 - ae)) / max(aOut, 0.0001);
float aOut2 = aOut + ao * (1.0 - aOut);
cOut = (cOut * aOut + LineColor.rgb * ao * (1.0 - aOut)) / max(aOut2, 0.0001);

float aTot = aIn + aOut2 * (1.0 - aIn);
float3 cTot = (col * aIn + cOut * aOut2 * (1.0 - aIn)) / max(aTot, 0.0001);
return float4(cTot, aTot);
