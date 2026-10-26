#include "UI/VM_Race.h"

const FName UVM_Race::CollectionName(TEXT("Race"));

// Поменять FText-поле, только если изменилось содержимое: FText в MVVM сравнивается по идентичности
#define VMR_SET_TEXT(Member, NewText) \
	if (TextDiffers(Member, NewText)) { UE_MVVM_SET_PROPERTY_VALUE(Member, NewText); }

bool UVM_Race::TextDiffers(const FText& Current, const FText& New)
{
	return !Current.IdenticalTo(New) && !Current.ToString().Equals(New.ToString(), ESearchCase::CaseSensitive);
}

void UVM_Race::SetRace(bool bNewInRace, int32 CompletedLaps, float LapFraction, int32 LapsToWin)
{
	UE_MVVM_SET_PROPERTY_VALUE(bInRace, bNewInRace && LapsToWin > 0);
	if (!bInRace)
	{
		return;
	}

	const bool bFinished = CompletedLaps >= LapsToWin;
	const int32 Lap      = FMath::Clamp(CompletedLaps + 1, 1, LapsToWin);
	const int32 LapsLeft = LapsToWin - Lap; // круги ПОСЛЕ текущего: на 2/3 — «1 LAP LEFT»

	VMR_SET_TEXT(LapNumText,   FText::AsNumber(Lap));
	VMR_SET_TEXT(LapTotalText, FText::FromString(FString::Printf(TEXT("/%d"), LapsToWin)));
	UE_MVVM_SET_PROPERTY_VALUE(LapsTotal, LapsToWin);

	const float Fill = bFinished
		? 1.0f
		: FMath::Clamp((CompletedLaps + FMath::Clamp(LapFraction, 0.0f, 1.0f)) / LapsToWin, 0.0f, 1.0f);
	if (!FMath::IsNearlyEqual(LapsFill, Fill, 0.001f))
	{
		UE_MVVM_SET_PROPERTY_VALUE(LapsFill, Fill);
	}

	FString Left;
	if (bFinished)
	{
		Left = TEXT("FINISHED");
	}
	else if (LapsLeft <= 0)
	{
		Left = TEXT("FINAL LAP");
	}
	else
	{
		Left = FString::Printf(TEXT("%d %s LEFT"), LapsLeft, LapsLeft == 1 ? TEXT("LAP") : TEXT("LAPS"));
	}
	VMR_SET_TEXT(LapLeftText, FText::FromString(Left));
	UE_MVVM_SET_PROPERTY_VALUE(bFinalLap, bFinished || LapsLeft <= 0);
}

#undef VMR_SET_TEXT
