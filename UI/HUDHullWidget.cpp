#include "UI/HUDHullWidget.h"
#include "UI/HUDRestoreAnim.h"
#include "UI/VM_BoatStatus.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "Materials/MaterialInstanceDynamic.h"

using namespace HUDRestoreAnim;

namespace HullRestore
{
	// Чип «+30»: держится 0.9 с, гаснет 0.5 с, поднимается на 14 px за 1.4 с — вся анимация кончается к этому
	constexpr float ChipHold = 0.9f;
	constexpr float ChipFade = 0.5f;
	constexpr float ChipRise = 14.0f;
	constexpr float Life     = ChipHold + ChipFade;

	// Яркий край шкалы, пока она растёт, и число, которое возвращается из зелёного в свой цвет
	const FLinearColor HeadColor(0.822786f, 1.0f, 0.887923f, 1.0f);   // #EAFFF2
	constexpr float NumberDelay = 0.5f;
	constexpr float NumberFade  = 0.6f;

	// След урона (M_UI_SegBar Trail, его пишет привязка HealthTrail): на хилке ABoatHUD сразу ставит его в новое
	// значение, и между растущей шкалой и следом встал бы светлый «призрак» — пока растём, след = шкала
	const FName Trail(TEXT("Trail"));
}

void UHUDHullWidget::NativeConstruct()
{
	Super::NativeConstruct();
	if (HullGainText)
	{
		HullGainText->SetVisibility(ESlateVisibility::Collapsed);
	}
}

void UHUDHullWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
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

	const float Pct = VM->GetHealthPercent();
	const float Max = VM->MaxHealth;

	// Восполнение — только при той же лодке и том же максимуме: возрождение и смена лодки дают скачок 0 → 100 %
	if (bPrevValid && VM->bHasBoat && FMath::IsNearlyEqual(Max, PrevMax) && PrevPct > 0.0f
		&& Pct - PrevPct >= MinGainFraction)
	{
		StartRestore(Age >= 0.0f ? FMath::Min(FromPct, PrevPct) : PrevPct, (Pct - PrevPct) * Max);
	}
	bPrevValid = VM->bHasBoat && Max > 0.0f;
	PrevPct    = Pct;
	PrevMax    = Max;

	if (Age >= 0.0f)
	{
		TickRestore(InDeltaTime, VM);
	}
}

void UHUDHullWidget::StartRestore(float InFromPct, float Amount)
{
	FromPct = InFromPct;
	Age     = 0.0f;

	if (HullGainText)
	{
		HullGainText->SetText(FText::FromString(FString::Printf(TEXT("+%d"), FMath::RoundToInt(Amount))));
		HullGainText->SetColorAndOpacity(FSlateColor(RestoreColor));
		HullGainText->SetVisibility(ESlateVisibility::HitTestInvisible);
	}
	if (UMaterialInstanceDynamic* Panel = GetMID(ImageBg))
	{
		Panel->SetScalarParameterValue(InnerGlowPx, GlowPx);
	}
}

void UHUDHullWidget::TickRestore(float DeltaTime, const UVM_BoatStatus* VM)
{
	Age += DeltaTime;
	const float Pct = VM->GetHealthPercent();

	// Урон посреди анимации опустил здоровье ниже старта — анимировать нечего
	if (Age >= HullRestore::Life || Pct <= FromPct)
	{
		StopRestore(VM);
		return;
	}

	// Шкала: растёт от старта к ТЕКУЩЕМУ значению (урон во время роста учтён), новая часть зелёная → остывает
	const float Shown = FMath::Lerp(FromPct, Pct, EaseOut(Age / GrowTime));
	if (UMaterialInstanceDynamic* Bar = GetMID(HullBar))
	{
		const float Cool = FMath::Clamp((Age - CoolDelay) / CoolTime, 0.0f, 1.0f);
		const float Head = Age < GrowTime ? 1.0f : FMath::Clamp(1.0f - (Age - GrowTime) / 0.25f, 0.0f, 1.0f);
		Bar->SetScalarParameterValue(Fill, Shown);
		Bar->SetScalarParameterValue(HullRestore::Trail, Shown);
		Bar->SetScalarParameterValue(GainFrom, FromPct);
		Bar->SetVectorParameterValue(GainColor, FLinearColor(RestoreColor.R, RestoreColor.G, RestoreColor.B, 1.0f - Cool));
		Bar->SetVectorParameterValue(GainHeadColor, FLinearColor(HullRestore::HeadColor.R, HullRestore::HeadColor.G, HullRestore::HeadColor.B, Head));
	}

	if (UMaterialInstanceDynamic* Panel = GetMID(ImageBg))
	{
		const float Glow = Bump(Age / GlowTime);
		Panel->SetVectorParameterValue(InnerGlowColor, FLinearColor(RestoreColor.R, RestoreColor.G, RestoreColor.B, GlowAlpha * Glow));
	}

	if (HullValue)
	{
		// Число считает вместе со шкалой — формат как у VM («15,000»: целое, запятая)
		FString Digits = FString::FromInt(FMath::RoundToInt(Shown * VM->MaxHealth));
		for (int32 Pos = Digits.Len() - 3; Pos > 0; Pos -= 3)
		{
			Digits.InsertAt(Pos, TEXT(','));
		}
		HullValue->SetText(FText::FromString(Digits));
		const float Back = FMath::Clamp((Age - HullRestore::NumberDelay) / HullRestore::NumberFade, 0.0f, 1.0f);
		HullValue->SetColorAndOpacity(FSlateColor(FMath::Lerp(RestoreColor, TargetValueColor(VM), Back)));
	}

	if (HullGainText)
	{
		HullGainText->SetRenderOpacity(ChipAlpha(Age, HullRestore::ChipHold, HullRestore::ChipFade));
		HullGainText->SetRenderTranslation(FVector2D(0.0, -HullRestore::ChipRise * EaseOut(Age / HullRestore::Life)));
	}
}

void UHUDHullWidget::StopRestore(const UVM_BoatStatus* VM)
{
	Age = -1.0f;

	// Возвращаем всё, что писали поверх привязок: шкалу и текст — к значениям VM
	if (UMaterialInstanceDynamic* Bar = GetMID(HullBar))
	{
		Bar->SetScalarParameterValue(Fill, VM ? VM->GetHealthPercent() : 0.0f);
		Bar->SetScalarParameterValue(HullRestore::Trail, VM ? VM->HealthTrail : 0.0f);
		Bar->SetScalarParameterValue(GainFrom, -1.0f);
		Bar->SetVectorParameterValue(GainColor, FLinearColor(RestoreColor.R, RestoreColor.G, RestoreColor.B, 0.0f));
		Bar->SetVectorParameterValue(GainHeadColor, FLinearColor(HullRestore::HeadColor.R, HullRestore::HeadColor.G, HullRestore::HeadColor.B, 0.0f));
	}
	if (UMaterialInstanceDynamic* Panel = GetMID(ImageBg))
	{
		Panel->SetVectorParameterValue(InnerGlowColor, FLinearColor(RestoreColor.R, RestoreColor.G, RestoreColor.B, 0.0f));
	}
	if (HullValue)
	{
		if (VM)
		{
			HullValue->SetText(VM->HealthText);
		}
		HullValue->SetColorAndOpacity(FSlateColor(TargetValueColor(VM)));
	}
	if (HullGainText)
	{
		HullGainText->SetVisibility(ESlateVisibility::Collapsed);
	}
}

FLinearColor UHUDHullWidget::TargetValueColor(const UVM_BoatStatus* VM) const
{
	// По VM, а не по цвету со старта: хилка может вывести из CRITICAL — тогда число уже не красное
	return (VM && VM->bHullCritical) ? ValueCriticalColor : ValueColor;
}
