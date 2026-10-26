#include "UI/VM_Drive.h"

const FName UVM_Drive::CollectionName(TEXT("Drive"));

void UVM_Drive::SetSpeed(float SpeedKmhFloat, float BarMaxKmh)
{
	const int32 Kmh = FMath::Clamp(FMath::RoundToInt(SpeedKmhFloat), 0, 999);

	// Тексты пересобираем только при смене целого значения: 20 раз в секунду FText не создаём
	if (UE_MVVM_SET_PROPERTY_VALUE(SpeedKmh, Kmh))
	{
		const FString Digits = FString::FromInt(Kmh);
		UE_MVVM_SET_PROPERTY_VALUE(SpeedLead,   FText::FromString(FString::ChrN(FMath::Max(0, 3 - Digits.Len()), TEXT('0'))));
		UE_MVVM_SET_PROPERTY_VALUE(SpeedDigits, FText::FromString(Digits));
	}

	// Шкала идёт по 22 сегментам — менее 0.005 глазом не видно, не будим виджет зря
	const float NewFill = BarMaxKmh > 0.0f ? FMath::Clamp(SpeedKmhFloat / BarMaxKmh, 0.0f, 1.0f) : 0.0f;
	if (!FMath::IsNearlyEqual(SpeedFill, NewFill, 0.005f))
	{
		UE_MVVM_SET_PROPERTY_VALUE(SpeedFill, NewFill);
	}
}

void UVM_Drive::SetNitro(float Nitro, float MaxNitro)
{
	const float Fill = MaxNitro > 0.0f ? FMath::Clamp(Nitro / MaxNitro, 0.0f, 1.0f) : 0.0f;
	UE_MVVM_SET_PROPERTY_VALUE(NitroFill, Fill);

	// FText сравнивается по идентичности: новый текст «76%» считался бы изменением на каждом
	// событии нитро (во время буста — каждый кадр). Пересобираем только при смене процента.
	const int32 Pct = FMath::RoundToInt(Fill * 100.0f);
	if (Pct != LastNitroPct)
	{
		LastNitroPct = Pct;
		UE_MVVM_SET_PROPERTY_VALUE(NitroPercentText, FText::FromString(FString::Printf(TEXT("%d%%"), Pct)));
	}
	UE_MVVM_SET_PROPERTY_VALUE(bNitroEmpty, Pct <= 0);
}

void UVM_Drive::SetBoost(bool bNewBoost)
{
	UE_MVVM_SET_PROPERTY_VALUE(bBoost, bNewBoost);
}
