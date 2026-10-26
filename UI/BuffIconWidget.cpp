#include "UI/BuffIconWidget.h"
#include "AbilitySystemComponent.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "Components/Border.h"
#include "Engine/Texture2D.h"
#include "GAS/DebuffLibrary.h"
#include "GameplayEffect.h"
#include "UI/DebuffContainerWidget.h"
#include "Animation/WidgetAnimation.h"
#include "Materials/MaterialInstanceDynamic.h"

// Значения — из компонента DebuffStacks дизайн-системы HUD (README + bundle.css), линейные цвета
namespace DebuffBadgeStyle
{
	/** glass-strong rgba(8,22,27,.86) */
	const FLinearColor Glass(0.0024f, 0.008f, 0.011f, 0.86f);
	/** Вспышка фона: rgba(192,140,255,.28) поверх glass-strong */
	constexpr float HitOverlayAlpha = 0.28f;
	/** Обводка: 1 px α.35 → максимум 1.5 px α.85 → попадание 1.5 px α1 */
	constexpr float StrokeW = 1.0f, StrokeA = 0.35f, MaxStrokeW = 1.5f, MaxStrokeA = 0.85f, HitStrokeW = 1.5f;
	/** Внутреннее свечение при попадании: 14 px α.55 */
	constexpr float HitGlowPx = 14.0f, HitGlowA = 0.55f;
	/** Свечение пипсов на максимуме α.8 */
	constexpr float MaxPipsGlowA = 0.8f;
	/** Обводка чипа: α.45 цветом дебаффа; у потолка — светлая α.55 */
	constexpr float ChipStrokeA = 0.45f, ChipCapStrokeA = 0.55f;

	FLinearColor WithAlpha(const FLinearColor& C, float A) { return FLinearColor(C.R, C.G, C.B, A); }
}

void UBuffIconWidget::Setup(UAbilitySystemComponent* InASC,
                             FActiveGameplayEffectHandle InHandle,
                             float InDuration,
                             UTexture2D* InIcon)
{
	TrackedASC  = InASC;
	Handle      = InHandle;
	FullDuration = FMath::Max(InDuration, 0.01f); // Защита от деления на ноль
	if (IsValid(TimeText))
	{
		DefaultTimeColor = TimeText->GetColorAndOpacity().GetSpecifiedColor();
	}

	// Установить иконку
	if (IsValid(IconImage) && IsValid(InIcon))
	{
		IconImage->SetBrushFromTexture(InIcon);
	}

	// Начальный тик таймера — Percent=1 (только что применён)
	BP_OnTimerTick(1.f, FullDuration);

	BP_OnSetup(FullDuration);
}

void UBuffIconWidget::ApplyStyle(const FHUDDebuffStyle& Style, const FText& Name)
{
	StyleColor         = Style.Color;
	bHasStyle          = true;
	bValueIsMultiplier = Style.bValueIsMultiplier;
	ValueTag           = Style.ValueTag;
	ValueScale         = Style.ValueScale;
	ValueFormat        = Style.ValueFormat;
	ShownValue         = -1;
	ShownStacks        = -1;
	bVisualDirty       = true;

	// Лимит и потолок — из того же правила, по которому дебафф накладывается: числа в одном месте
	MaxStacks        = Style.Rule ? FMath::Max(1, Style.Rule->MagnitudePerStack.Num()) : 1;
	BarMaxSeconds    = Style.Rule ? Style.Rule->MaxRemaining : 0.0f;
	StyleRule        = Style.Rule.Get();
	ShownCapFraction = -1.0f;

	if (IsValid(IconImage))
	{
		if (IsValid(Style.Icon))
		{
			IconImage->SetBrushFromTexture(Style.Icon);
		}
		IconImage->SetColorAndOpacity(StyleColor);
	}
	if (IsValid(NameText))
	{
		NameText->SetText(Name);
	}
	if (IsValid(ModText))
	{
		ModText->SetVisibility(ValueTag.IsValid() ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}
	if (IsValid(StackText))
	{
		StackText->SetColorAndOpacity(FSlateColor(StyleColor));
	}

	PanelMID  = IsValid(FillBg)     ? FillBg->GetDynamicMaterial()     : nullptr;
	PipsMID   = IsValid(StackPips)  ? StackPips->GetDynamicMaterial()  : nullptr;
	ChipBgMID = IsValid(BumpChipBg) ? BumpChipBg->GetDynamicMaterial() : nullptr;

	if (PipsMID)
	{
		PipsMID->SetScalarParameterValue(TEXT("Segments"), static_cast<float>(MaxStacks));
		PipsMID->SetVectorParameterValue(TEXT("OnColor"), StyleColor);
	}
	if (IsValid(StackPips))
	{
		StackPips->SetVisibility(MaxStacks > 1 ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}
	if (UWidget* Chip = IsValid(BumpChip) ? BumpChip.Get() : BumpText.Get())
	{
		Chip->SetVisibility(ESlateVisibility::Collapsed);
	}

	// Сразу показать силу и стаки, не дожидаясь тика
	const UAbilitySystemComponent* ASC = TrackedASC.Get();
	if (const FActiveGameplayEffect* ActiveGE = ASC ? ASC->GetActiveGameplayEffect(Handle) : nullptr)
	{
		RefreshValueAndStacks(*ActiveGE);
	}
	UpdateVisuals(0.0f);
}

void UBuffIconWidget::RefreshValueAndStacks(const FActiveGameplayEffect& ActiveGE)
{
	if (IsValid(ModText) && ValueTag.IsValid())
	{
		const float Raw = ActiveGE.Spec.GetSetByCallerMagnitude(ValueTag, false, bValueIsMultiplier ? 1.0f : 0.0f);
		// Множитель 0.8 → потеря 0.2 → «20»; знак рисует формат («−{0}%»)
		const int32 Value = FMath::RoundToInt(FMath::Abs((bValueIsMultiplier ? 1.0f - Raw : Raw) * ValueScale));
		if (Value != ShownValue)
		{
			ShownValue = Value;
			ModText->SetText(FText::Format(ValueFormat, FText::AsNumber(Value)));
		}
	}

	// Пипсы — путь до потолка силы: сила меняется и без нового стака (сильное оружие поверх слабого)
	const UDebuffRule* Rule = StyleRule.Get();
	const bool bCapPips = Rule && Rule->bStackToCap;
	if (bCapPips)
	{
		const float Magnitude = ActiveGE.Spec.GetSetByCallerMagnitude(Rule->MagnitudeTag, false, Rule->NeutralMagnitude);
		const float Fraction  = Rule->GetCapFraction(Magnitude);
		if (!FMath::IsNearlyEqual(Fraction, ShownCapFraction, 0.001f))
		{
			ShownCapFraction = Fraction;
			bVisualDirty     = true;
			if (PipsMID)
			{
				PipsMID->SetScalarParameterValue(TEXT("Fill"), Fraction);
			}
		}
	}

	const int32 Stacks = UDebuffLibrary::GetDebuffStacks(TrackedASC.Get(), Handle);
	if (Stacks != ShownStacks)
	{
		// Рост после первого показа — попадание; первый показ (−1) попаданием не считается
		if (ShownStacks > 0 && Stacks > ShownStacks)
		{
			bPendingStackAdded = true;
		}
		ShownStacks  = Stacks;
		bVisualDirty = true;

		if (IsValid(StackText))
		{
			StackText->SetText(FText::FromString(FString::Printf(TEXT("×%d"), Stacks)));
			StackText->SetVisibility(Stacks > 1 ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
		}
		if (PipsMID && !bCapPips)
		{
			PipsMID->SetScalarParameterValue(TEXT("Fill"), static_cast<float>(FMath::Min(Stacks, MaxStacks)) / MaxStacks);
		}
		BP_OnStacksChanged(Stacks, MaxStacks);
	}
}

bool UBuffIconWidget::IsAtMax() const
{
	const UDebuffRule* Rule = StyleRule.Get();
	if (Rule && Rule->bStackToCap)
	{
		return ShownCapFraction >= 0.999f;
	}
	return MaxStacks > 1 && ShownStacks >= MaxStacks;
}

void UBuffIconWidget::OnBump(float AddedSeconds, bool bStackAdded, bool bHitCap)
{
	HitTime        = 0.0f;
	bHitAddedStack = bStackAdded;
	if (bHitCap)
	{
		CapTime = 0.0f;
	}

	// Чип: сколько реально добавилось; у потолка «· MAX», если уже было 6.0 — просто «MAX»
	if (IsValid(BumpText))
	{
		FString Chip;
		if (AddedSeconds >= 0.05f)
		{
			Chip = FString::Printf(TEXT("+%.1fs"), AddedSeconds);
		}
		if (bHitCap)
		{
			Chip += Chip.IsEmpty() ? TEXT("MAX") : TEXT(" · MAX");
		}
		if (!Chip.IsEmpty())
		{
			BumpText->SetText(FText::FromString(Chip));
			ChipTime = 0.0f;
			bChipCap = bHitCap;

			// Цвета чипа на всё время анимации: у потолка — светлый текст и светлая обводка
			using namespace DebuffBadgeStyle;
			const FLinearColor TextColor   = bHitCap ? DefaultTimeColor : StyleColor;
			const FLinearColor StrokeColor = bHitCap ? WithAlpha(DefaultTimeColor, ChipCapStrokeA) : WithAlpha(StyleColor, ChipStrokeA);
			BumpText->SetColorAndOpacity(FSlateColor(TextColor));
			if (ChipBgMID)
			{
				ChipBgMID->SetVectorParameterValue(TEXT("StrokeColor"), StrokeColor);
			}
			else if (UBorder* ChipBorder = Cast<UBorder>(BumpChip.Get()))
			{
				// Чип-Border растягивается под текст — обводку берём из его кисти
				FSlateBrush Brush = ChipBorder->Background;
				Brush.OutlineSettings.Color = FSlateColor(StrokeColor);
				ChipBorder->SetBrush(Brush);
			}
		}
	}

	if (BumpAnim)
	{
		PlayAnimation(BumpAnim);
	}
	BP_OnBumped(AddedSeconds, bStackAdded, bHitCap);
}

void UBuffIconWidget::UpdateVisuals(float DeltaTime)
{
	using namespace DebuffBadgeStyle;

	const bool bAnimating = HitTime >= 0.f || CapTime >= 0.f || ChipTime >= 0.f;
	if (!bAnimating && !bVisualDirty)
	{
		return; // нечего перекрашивать — не будим Slate каждый кадр
	}
	bVisualDirty = false;

	auto Advance = [DeltaTime](float& Time, float Duration)
	{
		if (Time >= 0.f)
		{
			Time += DeltaTime;
			if (Time >= Duration)
			{
				Time = -1.f;
			}
		}
	};
	Advance(HitTime,  HitDuration);
	Advance(CapTime,  CapFlashDuration);
	Advance(ChipTime, ChipDuration);
	if (!(HitTime >= 0.f || CapTime >= 0.f || ChipTime >= 0.f))
	{
		bVisualDirty = true; // анимации только что кончились — ещё один проход, чтобы встать в покой
	}

	// ease-out: пик в начале, к концу плавно в покой
	const float HitW   = HitTime >= 0.f ? FMath::Square(1.f - HitTime / HitDuration) : 0.f;
	// Фон/обводка вспыхивают при любом попадании (и на максимуме стаков); белый пипс — только новый стак
	const float StackW = bHitAddedStack ? HitW : 0.f;
	// Потолок: белое сразу и плавно (smoothstep) обратно в свой цвет за CapFlashDuration
	const float CapW   = CapTime >= 0.f ? 1.f - FMath::SmoothStep(0.f, 1.f, CapTime / CapFlashDuration) : 0.f;
	const bool  bMax   = IsAtMax();
	const FLinearColor C = StyleColor;

	if (PanelMID)
	{
		const float BaseW = bMax ? MaxStrokeW : StrokeW;
		const float BaseA = bMax ? MaxStrokeA : StrokeA;
		PanelMID->SetScalarParameterValue(TEXT("StrokeW"), FMath::Lerp(BaseW, HitStrokeW, HitW));
		PanelMID->SetVectorParameterValue(TEXT("StrokeColor"), WithAlpha(C, FMath::Lerp(BaseA, 1.f, HitW)));
		PanelMID->SetScalarParameterValue(TEXT("InnerGlowPx"), HitGlowPx);
		PanelMID->SetVectorParameterValue(TEXT("InnerGlowColor"), WithAlpha(C, HitGlowA * HitW));

		// Фиолетовый слой α.28 поверх стекла — одним цветом, как сложились бы два слоя
		const float OutA = HitOverlayAlpha + Glass.A * (1.f - HitOverlayAlpha);
		const FLinearColor HitRGB = (C * HitOverlayAlpha + Glass * (Glass.A * (1.f - HitOverlayAlpha))) / OutA;
		const FLinearColor HitFill = WithAlpha(HitRGB, OutA);
		PanelMID->SetVectorParameterValue(TEXT("Fill"), FMath::Lerp(Glass, HitFill, HitW));
	}

	if (PipsMID)
	{
		// Новый пипс (последний горящий, PeakColor) — белый и гаснет в цвет стака
		PipsMID->SetVectorParameterValue(TEXT("PeakColor"), FLinearColor(1.f, 1.f, 1.f, StackW));
		PipsMID->SetVectorParameterValue(TEXT("GlowColor"), WithAlpha(C, bMax ? MaxPipsGlowA : 0.f));
	}

	if (IsValid(ModText))
	{
		ModText->SetColorAndOpacity(FSlateColor(FMath::Lerp(C, FLinearColor::White, HitW)));
	}
	if (IsValid(TimeText))
	{
		// Время белеет при любом попадании; у потолка — белое и плавно возвращается вместе с полоской
		const FLinearColor BaseTime = bEnding ? C : DefaultTimeColor;
		const float White = FMath::Max(HitW, CapW);
		TimeText->SetColorAndOpacity(FSlateColor(FMath::Lerp(BaseTime, FLinearColor::White, White)));
	}
	if (IsValid(TimerBar))
	{
		// Упёрлись в потолок — полоска белая и плавно возвращается в цвет дебаффа
		TimerBar->SetColorAndOpacity(FMath::Lerp(C, FLinearColor::White, CapW));
	}

	// Чип: поднимается на ChipRise и гаснет
	UWidget* ChipWidget = IsValid(BumpChip) ? BumpChip.Get() : BumpText.Get();
	if (ChipWidget)
	{
		if (ChipTime >= 0.f)
		{
			const float T = ChipTime / ChipDuration;
			ChipWidget->SetVisibility(ESlateVisibility::HitTestInvisible);
			ChipWidget->SetRenderTranslation(FVector2D(0.f, ChipOffsetY - ChipRise * T));
			ChipWidget->SetRenderOpacity(1.f - T);
		}
		else
		{
			ChipWidget->SetVisibility(ESlateVisibility::Collapsed);
		}
	}

}

void UBuffIconWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	UAbilitySystemComponent* ASC = TrackedASC.Get();
	if (!IsValid(ASC) || !Handle.IsValid())
	{
		return;
	}

	// Получить активный эффект
	const FActiveGameplayEffect* ActiveGE = ASC->GetActiveGameplayEffect(Handle);
	if (!ActiveGE)
	{
		return;
	}

	// Получить реально оставшееся время
	const float Remaining = ActiveGE->GetTimeRemaining(GetWorld()->GetTimeSeconds());

	// Infinite-эффект (-1) — передаём Percent=1, Remaining=-1
	if (Remaining < 0.f)
	{
		BP_OnTimerTick(1.f, -1.f);
		return;
	}

	// Продлили (ApplyStackingDebuff): без правила полоска снова полная от нового остатка
	if (Remaining > FullDuration)
	{
		FullDuration = Remaining;
	}

	if (bHasStyle)
	{
		RefreshValueAndStacks(*ActiveGE);
	}

	// Повторное попадание: стак вырос и/или остаток скакнул вверх. Добавка — разница с прошлым тиком
	// плюс прошедшее время (за тик остаток и так уменьшился на DeltaTime)
	const bool bExtended = PrevRemaining >= 0.f && Remaining > PrevRemaining + 0.05f;
	if (bExtended || bPendingStackAdded)
	{
		const float Added  = bExtended ? FMath::Max(0.f, Remaining - (PrevRemaining - InDeltaTime)) : 0.f;
		const bool bHitCap = BarMaxSeconds > 0.f && Remaining >= BarMaxSeconds - 0.05f;
		OnBump(Added, bPendingStackAdded, bHitCap);

		// Полоска снова полная и отсчитывает от нового остатка: больше времени — медленнее тает
		FullDuration = FMath::Max(Remaining, 0.01f);
	}
	PrevRemaining      = Remaining;
	bPendingStackAdded = false;

	// Последняя секунда: время цветом дебаффа (без мигания — решение 2026-10-06); продлили — снято
	const bool bNowEnding = Remaining <= 1.f;
	if (bNowEnding != bEnding)
	{
		bEnding      = bNowEnding;
		bVisualDirty = true;
		if (bNowEnding && !bExpiringNotified)
		{
			bExpiringNotified = true;
			BP_OnExpiring();
		}
		if (!bNowEnding)
		{
			bExpiringNotified = false;
		}
	}

	if (bHasStyle)
	{
		UpdateVisuals(InDeltaTime);
	}

	// Прогресс 1.0 → 0.0 от остатка на момент последнего попадания (решение 2026-10-06 вместо шкалы до 6 с)
	const float Percent = FMath::Clamp(Remaining / FullDuration, 0.f, 1.f);

	// Render Scale, а не ширина: раскладку не двигает
	if (IsValid(TimerBar))
	{
		TimerBar->SetRenderScale(FVector2D(Percent, 1.0f));
	}

	// Вызвать Blueprint каждый тик — там обновляй параметр материала
	BP_OnTimerTick(Percent, FMath::Max(0.f, Remaining));

	// «3.2s» — всегда один знак после точки
	if (IsValid(TimeText))
	{
		TimeText->SetText(FText::FromString(FString::Printf(TEXT("%.1fs"), FMath::Max(0.f, Remaining))));
	}
}
