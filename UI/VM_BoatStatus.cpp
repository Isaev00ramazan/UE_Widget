#include "UI/VM_BoatStatus.h"

const FName UVM_BoatStatus::CollectionName(TEXT("BoatStatus"));

float UVM_BoatStatus::GetHealthPercent() const
{
	return MaxHealth > 0.0f ? FMath::Clamp(Health / MaxHealth, 0.0f, 1.0f) : 0.0f;
}

float UVM_BoatStatus::GetNitroPercent() const
{
	return MaxNitro > 0.0f ? FMath::Clamp(Nitro / MaxNitro, 0.0f, 1.0f) : 0.0f;
}

// Процент — вычисляемое поле: о его изменении сообщаем вместе с каждым из двух слагаемых,
// иначе полоска не узнала бы, что поменялся максимум (Custom HP приходит после BeginPlay лодки)

void UVM_BoatStatus::SetHealth(float NewValue)
{
	if (UE_MVVM_SET_PROPERTY_VALUE(Health, NewValue))
	{
		UE_MVVM_BROADCAST_FIELD_VALUE_CHANGED(GetHealthPercent);
		RefreshHealthDerived();
	}
}

void UVM_BoatStatus::SetMaxHealth(float NewValue)
{
	if (UE_MVVM_SET_PROPERTY_VALUE(MaxHealth, NewValue))
	{
		UE_MVVM_BROADCAST_FIELD_VALUE_CHANGED(GetHealthPercent);
		RefreshHealthDerived();
	}
}

namespace BoatStatusPrivate
{
	/** «15,000»: разделитель — запятая, как в макете. FText::AsNumber в русской культуре дал бы «15 000». */
	FString FormatThousands(int32 Value)
	{
		FString Digits = FString::FromInt(FMath::Abs(Value));
		for (int32 Pos = Digits.Len() - 3; Pos > 0; Pos -= 3)
		{
			Digits.InsertAt(Pos, TEXT(','));
		}
		return Value < 0 ? TEXT("-") + Digits : Digits;
	}

	bool TextDiffers(const FText& Current, const FString& New)
	{
		return !Current.ToString().Equals(New, ESearchCase::CaseSensitive);
	}
}

void UVM_BoatStatus::RefreshHealthDerived()
{
	using namespace BoatStatusPrivate;
	// Тексты сравниваем по строке: FText в MVVM сравнивается по идентичности, новый будил бы виджет зря
	const FString HealthStr = FormatThousands(FMath::RoundToInt(Health));
	if (TextDiffers(HealthText, HealthStr))
	{
		UE_MVVM_SET_PROPERTY_VALUE(HealthText, FText::FromString(HealthStr));
	}

	const FString MaxStr = TEXT("/") + FormatThousands(FMath::RoundToInt(MaxHealth));
	if (TextDiffers(MaxHealthText, MaxStr))
	{
		UE_MVVM_SET_PROPERTY_VALUE(MaxHealthText, FText::FromString(MaxStr));
	}

	// Мёртвая лодка (0) — тоже критично; без максимума (ещё не пришёл) — нет
	UE_MVVM_SET_PROPERTY_VALUE(bHullCritical, MaxHealth > 0.0f && GetHealthPercent() <= CriticalFraction);
}

void UVM_BoatStatus::SetHealthTrail(float NewValue)
{
	// 20 сегментов: шаг 0.002 глазом не виден — не будим виджет на каждом опросе
	if (!FMath::IsNearlyEqual(HealthTrail, NewValue, 0.002f))
	{
		UE_MVVM_SET_PROPERTY_VALUE(HealthTrail, NewValue);
	}
}

void UVM_BoatStatus::SetNitro(float NewValue)
{
	if (UE_MVVM_SET_PROPERTY_VALUE(Nitro, NewValue))
	{
		UE_MVVM_BROADCAST_FIELD_VALUE_CHANGED(GetNitroPercent);
	}
}

void UVM_BoatStatus::SetMaxNitro(float NewValue)
{
	if (UE_MVVM_SET_PROPERTY_VALUE(MaxNitro, NewValue))
	{
		UE_MVVM_BROADCAST_FIELD_VALUE_CHANGED(GetNitroPercent);
	}
}

void UVM_BoatStatus::SetHasBoat(bool bNewValue)
{
	UE_MVVM_SET_PROPERTY_VALUE(bHasBoat, bNewValue);
}
