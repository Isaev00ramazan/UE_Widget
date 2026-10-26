#include "UI/VM_AbilitySlot.h"

const FName UVM_AbilitySlot::MainCollectionName(TEXT("AbilityMain"));
const FName UVM_AbilitySlot::PerkCollectionName(TEXT("AbilityPerk"));

// Поменять FText-поле, только если изменилось содержимое: FText в MVVM сравнивается по идентичности
#define VMA_SET_TEXT(Member, NewText) \
	if (TextDiffers(Member, NewText)) { UE_MVVM_SET_PROPERTY_VALUE(Member, NewText); }

bool UVM_AbilitySlot::TextDiffers(const FText& Current, const FText& New)
{
	return !Current.IdenticalTo(New) && !Current.ToString().Equals(New.ToString(), ESearchCase::CaseSensitive);
}

void UVM_AbilitySlot::SetSlot(bool bNewHasSlot, const FText& Name, UTexture2D* NewIcon, EHUDAbilityState NewState,
                              float Progress, float Remaining)
{
	UE_MVVM_SET_PROPERTY_VALUE(bHasSlot, bNewHasSlot);
	if (!bHasSlot)
	{
		return;
	}

	UE_MVVM_SET_PROPERTY_VALUE(Icon, NewIcon);
	UE_MVVM_SET_PROPERTY_VALUE(State, NewState);

	const float Ring = FMath::Clamp(Progress, 0.0f, 1.0f);
	// Кольцо — около 340 px окружности: шаг 0.002 меньше пикселя
	if (!FMath::IsNearlyEqual(RingProgress, Ring, 0.002f))
	{
		UE_MVVM_SET_PROPERTY_VALUE(RingProgress, Ring);
	}

	// Секунды вверх: «1», пока не истекла последняя секунда (как в макете — целые)
	const FText Seconds = NewState == EHUDAbilityState::Cooldown
		? FText::AsNumber(FMath::Max(FMath::CeilToInt(Remaining), 1))
		: FText::GetEmpty();
	VMA_SET_TEXT(CooldownText, Seconds);

	const FText Label = NewState == EHUDAbilityState::Active
		? FText::FromString(FString::Printf(TEXT("%s %d%%"), *Name.ToString(), FMath::RoundToInt(Ring * 100.0f)))
		: Name;
	VMA_SET_TEXT(LabelText, Label);
}

#undef VMA_SET_TEXT
