#include "UI/MinimapSubsystem.h"
#include "Boat/BoatBase.h"

void UMinimapSubsystem::RegisterBoat(ABoatBase* Boat)
{
	if (Boat)
	{
		RegisteredBoats.AddUnique(Boat);
	}
}

void UMinimapSubsystem::UnregisterBoat(ABoatBase* Boat)
{
	RegisteredBoats.RemoveAll([Boat](const TWeakObjectPtr<ABoatBase>& Weak)
	{
		return !Weak.IsValid() || Weak.Get() == Boat;
	});
}

TArray<ABoatBase*> UMinimapSubsystem::GetActiveBoats() const
{
	TArray<ABoatBase*> Result;
	Result.Reserve(RegisteredBoats.Num());

	for (const TWeakObjectPtr<ABoatBase>& Weak : RegisteredBoats)
	{
		if (ABoatBase* Boat = Weak.Get())
		{
			Result.Add(Boat);
		}
	}

	return Result;
}
