#include "UI/RacePositionRowWidget.h"
#include "Boat/BoatBase.h"

void URacePositionRowWidget::SetupRow(int32 InPosition, ABoatBase* InBoat)
{
	Position = InPosition;
	Boat = InBoat;
	BP_OnRowUpdated(InPosition, InBoat);
}

bool URacePositionRowWidget::IsLocalPlayerBoat() const
{
	const ABoatBase* RowBoat = Boat.Get();
	return RowBoat && RowBoat->IsPlayerControlled() && RowBoat->IsLocallyControlled();
}

FText URacePositionRowWidget::GetRacerName() const
{
	if (IsLocalPlayerBoat())
	{
		return LocalPlayerName;
	}

	const ABoatBase* RowBoat = Boat.Get();
	if (RowBoat && !RowBoat->BoatDisplayName.IsEmpty())
	{
		return FText::FromString(RowBoat->BoatDisplayName);
	}
	return FallbackName;
}
