#include "UI/MinimapIconWidget.h"
#include "Boat/BoatBase.h"

void UMinimapIconWidget::Setup(ABoatBase* InBoat)
{
	OwningBoat = InBoat;
	BP_OnSetup(InBoat);
}
