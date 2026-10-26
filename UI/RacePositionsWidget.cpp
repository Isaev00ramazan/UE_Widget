#include "UI/RacePositionsWidget.h"
#include "UI/RacePositionRowWidget.h"
#include "Race/RaceManagerSubsystem.h"
#include "Boat/BoatBase.h"
#include "Components/PanelWidget.h"
#include "TimerManager.h"

void URacePositionsWidget::InitRacePositions()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(
			UpdateTimerHandle, this, &URacePositionsWidget::UpdateStandings,
			1.0f / FMath::Max(UpdateRateHz, 0.1f), true);
	}
}

void URacePositionsWidget::NativeDestruct()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(UpdateTimerHandle);
	}

	Super::NativeDestruct();
}

void URacePositionsWidget::UpdateStandings()
{
	if (!IsValid(RowContainer))
	{
		return;
	}

	UWorld* World = GetWorld();
	URaceManagerSubsystem* RaceManager = World ? World->GetSubsystem<URaceManagerSubsystem>() : nullptr;
	if (!RaceManager)
	{
		return;
	}

	if (!IsValid(RowWidgetClass))
	{
		UE_LOG(LogTemp, Warning, TEXT("RacePositionsWidget: RowWidgetClass не назначен в Blueprint!"));
		return;
	}

	const TArray<ABoatBase*> Standings = RaceManager->GetSortedStandings();

	// Убираем строки лодок, которых больше нет в гонке (сами виджеты держатся живыми через
	// RowWidgets, а не через контейнер — ниже он всё равно полностью пересобирается)
	for (auto It = RowWidgets.CreateIterator(); It; ++It)
	{
		ABoatBase* Boat = It.Key().Get();
		if (!Boat || !Standings.Contains(Boat))
		{
			It.RemoveCurrent();
		}
	}

	// Полная пересборка порядка вместо поштучного ShiftChild — так порядок детей в контейнере
	// гарантированно совпадает со Standings после каждого обновления, без каких-либо сомнений
	// в том, как конкретная панель обрабатывает точечную перестановку. Сами виджеты (Row) не
	// пересоздаются — ClearChildren только отвязывает их от панели, RowWidgets держит их живыми.
	RowContainer->ClearChildren();

	// Место = индекс в Standings + 1, даже если среди лодок есть невалидные — как было
	TArray<TPair<int32, ABoatBase*>> Visible;
	for (int32 Index = 0; Index < Standings.Num(); ++Index)
	{
		if (IsValid(Standings[Index]))
		{
			Visible.Emplace(Index + 1, Standings[Index]);
		}
	}

	if (MaxRows > 0 && Visible.Num() > MaxRows)
	{
		const APawn* LocalPawn = GetOwningPlayerPawn();
		const int32 LocalIndex = Visible.IndexOfByPredicate([LocalPawn](const TPair<int32, ABoatBase*>& Entry)
		{
			return Entry.Value == LocalPawn;
		});

		if (bAlwaysShowLocalPlayer && LocalIndex >= MaxRows)
		{
			// Игрок должен видеть своё место всегда: последняя строка — его, с настоящим номером
			const TPair<int32, ABoatBase*> LocalEntry = Visible[LocalIndex];
			Visible.SetNum(MaxRows - 1);
			Visible.Add(LocalEntry);
		}
		else
		{
			Visible.SetNum(MaxRows);
		}
	}

	// ⚠️ RowWidgets — не UPROPERTY: живыми строки держит только RowContainer. Строка, которая не попала
	// в видимые (ниже MaxRows), осталась бы без ссылок — GC удалил бы её, а в карте остался бы висячий
	// указатель (краш в AddChild, когда лодка снова поднималась в топ). Такие строки убираем из карты,
	// при возвращении в топ — создаём заново.
	for (auto It = RowWidgets.CreateIterator(); It; ++It)
	{
		const ABoatBase* Boat = It.Key().Get();
		const bool bVisible = Visible.ContainsByPredicate([Boat](const TPair<int32, ABoatBase*>& Entry)
		{
			return Entry.Value == Boat;
		});
		if (!bVisible)
		{
			It.RemoveCurrent();
		}
	}

	for (const TPair<int32, ABoatBase*>& Entry : Visible)
	{
		TObjectPtr<URacePositionRowWidget>& Row = RowWidgets.FindOrAdd(Entry.Value);
		if (!Row)
		{
			Row = CreateWidget<URacePositionRowWidget>(this, RowWidgetClass);
			if (!Row)
			{
				continue;
			}
		}

		RowContainer->AddChild(Row);
		Row->SetupRow(Entry.Key, Entry.Value);
	}
}
