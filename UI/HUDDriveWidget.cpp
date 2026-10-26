#include "UI/HUDDriveWidget.h"
#include "UI/HUDRestoreAnim.h"
#include "UI/VM_BoatStatus.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "Materials/MaterialInstanceDynamic.h"

using namespace HUDRestoreAnim;

namespace NitroRestore
{
	// Чип «+50»: держится 1 с, гаснет 0.4 с, поднимается на 10 px, на входе 1.3 → 1 за 0.25 с
	constexpr float ChipHold = 1.0f;
	constexpr float ChipFade = 0.4f;
	constexpr float ChipRise = 10.0f;
	constexpr float Life     = ChipHold + ChipFade;

	// Шкала на пике свечения: ореол ярче и шире (falloff вдвое мягче) — «0 0 20px α.8» доски поверх обычного
	constexpr float PeakGlowAlpha = 1.0f;
	constexpr float PeakFalloffK  = 0.5f;
}

void UHUDDriveWidget::NativeConstruct()
{
	Super::NativeConstruct();
	if (NitroGainText)
	{
		NitroGainText->SetVisibility(ESlateVisibility::Collapsed);
	}
}

void UHUDDriveWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	UVM_BoatStatus* VM = BoatStatus.Get();
	if (!VM)
	{
		VM = FindBoatStatus(this);
		BoatStatus = VM;
		if (!VM)
		{
			return;
		}
	}

	const float Pct = VM->GetNitroPercent();
	const float Max = VM->MaxNitro;

	// Та же лодка и тот же бак: смена лодки — не восполнение
	if (bPrevValid && VM->bHasBoat && FMath::IsNearlyEqual(Max, PrevMax) && Pct - PrevPct >= MinGainFraction)
	{
		StartRestore(Age >= 0.0f ? FMath::Min(FromPct, PrevPct) : PrevPct, Pct);
	}
	bPrevValid = VM->bHasBoat && Max > 0.0f;
	PrevPct    = Pct;
	PrevMax    = Max;

	if (Age >= 0.0f)
	{
		TickRestore(InDeltaTime, VM);
	}
}

void UHUDDriveWidget::StartRestore(float InFromPct, float ToPct)
{
	// Исходные значения — только на старте с нуля: посреди анимации они уже наши
	if (Age < 0.0f)
	{
		if (UMaterialInstanceDynamic* Bar = GetMID(NitroBar))
		{
			BaseGlowColor   = Bar->K2_GetVectorParameterValue(GlowColor);
			BaseGlowFalloff = Bar->K2_GetScalarParameterValue(GlowFalloff);
		}
		if (NitroIcon)
		{
			BaseIconTint = NitroIcon->GetBrush().TintColor.GetSpecifiedColor();
		}
	}
	FromPct = InFromPct;
	Age     = 0.0f;

	if (NitroGainText)
	{
		NitroGainText->SetText(FText::FromString(FString::Printf(TEXT("+%d"), FMath::RoundToInt((ToPct - InFromPct) * 100.0f))));
		NitroGainText->SetColorAndOpacity(FSlateColor(ChipColor));
		NitroGainText->SetVisibility(ESlateVisibility::HitTestInvisible);
	}
}

float UHUDDriveWidget::CrossTime(float D, float ToPct) const
{
	if (D <= FromPct || D > ToPct || ToPct - FromPct < KINDA_SMALL_NUMBER)
	{
		return -1.0f;
	}
	// Обратная к ease-out (1 − (1 − u)³): u = 1 − ∛(1 − k)
	const float K = (D - FromPct) / (ToPct - FromPct);
	return GrowTime * (1.0f - FMath::Pow(1.0f - K, 1.0f / 3.0f));
}

void UHUDDriveWidget::TickRestore(float DeltaTime, const UVM_BoatStatus* VM)
{
	Age += DeltaTime;
	const float Pct = VM->GetNitroPercent();

	// Нитро тратится и во время анимации — растём к текущему; упало ниже старта — анимировать нечего
	if (Age >= NitroRestore::Life || Pct <= FromPct)
	{
		StopRestore(VM);
		return;
	}

	const float Shown = FMath::Lerp(FromPct, Pct, EaseOut(Age / GrowTime));
	if (UMaterialInstanceDynamic* Bar = GetMID(NitroBar))
	{
		Bar->SetScalarParameterValue(Fill, Shown);

		// Деления — на k / Segments; каждое вспыхивает, когда шкала его пересекла
		const float Segs = FMath::Max(Bar->K2_GetScalarParameterValue(Segments), 1.0f);
		float Flash[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
		for (int32 K = 0; K < 4 && K + 1 < Segs; ++K)
		{
			const float T = CrossTime((K + 1) / Segs, Pct);
			Flash[K] = (T >= 0.0f && Age >= T) ? FMath::Clamp(1.0f - (Age - T) / DivisionFlashTime, 0.0f, 1.0f) : 0.0f;
		}
		Bar->SetVectorParameterValue(GapFlash, FLinearColor(Flash[0], Flash[1], Flash[2], Flash[3]));

		const float Glow = Bump(Age / GlowTime);
		FLinearColor GlowC = BaseGlowColor;
		GlowC.A = FMath::Lerp(BaseGlowColor.A, NitroRestore::PeakGlowAlpha, Glow);
		Bar->SetVectorParameterValue(GlowColor, GlowC);
		Bar->SetScalarParameterValue(GlowFalloff, FMath::Lerp(BaseGlowFalloff, BaseGlowFalloff * NitroRestore::PeakFalloffK, Glow));
	}

	if (NitroPct)
	{
		// Формат как у VM_Drive («76%»)
		NitroPct->SetText(FText::FromString(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Shown * 100.0f))));
	}
	if (NitroIcon)
	{
		// Белой иконку делают оба множителя: и Brush Tint (синий в вёрстке), и Color and Opacity (синий от привязки)
		const float Back = FMath::Clamp(Age / IconFlashTime, 0.0f, 1.0f);
		NitroIcon->SetBrushTintColor(FSlateColor(FMath::Lerp(FLinearColor::White, BaseIconTint, Back)));
		NitroIcon->SetColorAndOpacity(FMath::Lerp(FLinearColor::White, IconColor, Back));
	}
	if (NitroGainText)
	{
		NitroGainText->SetRenderOpacity(ChipAlpha(Age, NitroRestore::ChipHold, NitroRestore::ChipFade));
		NitroGainText->SetRenderTranslation(FVector2D(0.0, -NitroRestore::ChipRise * EaseOut(Age / NitroRestore::Life)));
		const float Pop = 1.0f + 0.3f * (1.0f - EaseOut(Age / 0.25f));
		NitroGainText->SetRenderScale(FVector2D(Pop, Pop));
	}
}

void UHUDDriveWidget::StopRestore(const UVM_BoatStatus* VM)
{
	Age = -1.0f;

	// Возвращаем всё, что писали поверх привязок и MI
	const float Pct = VM ? VM->GetNitroPercent() : 0.0f;
	if (UMaterialInstanceDynamic* Bar = GetMID(NitroBar))
	{
		Bar->SetScalarParameterValue(Fill, Pct);
		Bar->SetVectorParameterValue(GapFlash, FLinearColor(0.0f, 0.0f, 0.0f, 0.0f));
		Bar->SetVectorParameterValue(GlowColor, BaseGlowColor);
		Bar->SetScalarParameterValue(GlowFalloff, BaseGlowFalloff);
	}
	if (NitroPct)
	{
		NitroPct->SetText(FText::FromString(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Pct * 100.0f))));
	}
	if (NitroIcon)
	{
		NitroIcon->SetBrushTintColor(FSlateColor(BaseIconTint));
		NitroIcon->SetColorAndOpacity(IconColor);
	}
	if (NitroGainText)
	{
		NitroGainText->SetVisibility(ESlateVisibility::Collapsed);
	}
}
