#include "UI/RaceResultsWidget.h"
#include "Race/RaceGameState.h"
#include "Race/RaceManagerSubsystem.h"
#include "Boat/BoatBase.h"
#include "SplineRoad.h"
#include "Components/Image.h"
#include "Components/PanelWidget.h"
#include "Components/SplineComponent.h"
#include "Components/TextBlock.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "TimerManager.h"

namespace
{
	FString FormatThousands(int32 Value)
	{
		FString Digits = FString::FromInt(FMath::Abs(Value));
		for (int32 Pos = Digits.Len() - 3; Pos > 0; Pos -= 3)
		{
			Digits.InsertAt(Pos, TEXT(','));
		}
		return Value < 0 ? TEXT("-") + Digits : Digits;
	}

	/** 1st, 2nd, 3rd, 4th … 11th–13th */
	FString OrdinalSuffix(int32 N)
	{
		const int32 Mod100 = N % 100;
		if (Mod100 >= 11 && Mod100 <= 13)
		{
			return TEXT("th");
		}
		switch (N % 10)
		{
		case 1:  return TEXT("st");
		case 2:  return TEXT("nd");
		case 3:  return TEXT("rd");
		default: return TEXT("th");
		}
	}

	FText RacerName(const ABoatBase* Boat, bool bLocal)
	{
		// ⚠️ Не PlayerState->GetPlayerName(): офлайн там имя компьютера
		if (!Boat->BoatDisplayName.IsEmpty())
		{
			return FText::FromString(Boat->BoatDisplayName);
		}
		return bLocal ? NSLOCTEXT("RaceResults", "PlayerFallback", "Player")
		              : NSLOCTEXT("RaceResults", "BotFallback", "Bot");
	}

	void SetText(UTextBlock* Text, const FText& Value)
	{
		if (Text)
		{
			Text->SetText(Value);
		}
	}
}

// =====================================================================
// ДАННЫЕ
// =====================================================================

void URaceResultsWidget::BuildEntries(const UObject* WorldContextObject, const APawn* LocalPawn, TArray<FRaceResultEntry>& OutEntries)
{
	OutEntries.Reset();

	const ARaceGameState* Race = ARaceGameState::GetRaceGameState(WorldContextObject);
	const UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	if (!Race || !World)
	{
		return;
	}

	const URaceManagerSubsystem* RaceManager = World->GetSubsystem<URaceManagerSubsystem>();
	const TArray<ABoatBase*> Standings = RaceManager ? RaceManager->GetSortedStandings() : TArray<ABoatBase*>();
	const USplineComponent* Spline = Race->TrackRoad ? Race->TrackRoad->SplineComponent.Get() : nullptr;
	const float TrackLength = Spline ? Spline->GetSplineLength() : 0.0f;

	// Лучший круг заезда — у всех, не только у финишировавших
	float FastestLap = 0.0f;
	for (const FRaceBoatStats& Stats : Race->BoatStats)
	{
		if (Stats.BestLapTime > 0.0f && (FastestLap <= 0.0f || Stats.BestLapTime < FastestLap))
		{
			FastestLap = Stats.BestLapTime;
		}
	}

	auto MakeEntry = [&](ABoatBase* Boat, const FRaceBoatStats* Stats)
	{
		FRaceResultEntry& Entry = OutEntries.AddDefaulted_GetRef();
		Entry.Boat           = Boat;
		Entry.Position       = OutEntries.Num();
		Entry.bIsLocalPlayer = Boat == LocalPawn;
		Entry.Name           = RacerName(Boat, Entry.bIsLocalPlayer);
		Entry.LapsTotal      = Race->LapsToWin;
		if (Stats)
		{
			Entry.BestLapTime = Stats->BestLapTime;
			Entry.bFastestLap = FastestLap > 0.0f && FMath::IsNearlyEqual(Stats->BestLapTime, FastestLap);
			Entry.Kills       = Stats->Kills;
		}
		return &Entry;
	};

	// Финишировавшие — по месту финиша
	TArray<const FRaceBoatStats*> Finished;
	for (const FRaceBoatStats& Stats : Race->BoatStats)
	{
		if (Stats.FinishPosition > 0 && IsValid(Stats.Boat))
		{
			Finished.Add(&Stats);
		}
	}
	Finished.Sort([](const FRaceBoatStats& A, const FRaceBoatStats& B) { return A.FinishPosition < B.FinishPosition; });

	const float LeaderTime = Finished.Num() > 0 ? Finished[0]->FinishTime : 0.0f;
	for (const FRaceBoatStats* Stats : Finished)
	{
		FRaceResultEntry* Entry = MakeEntry(Stats->Boat, Stats);
		Entry->State      = ERaceResultState::Finished;
		Entry->FinishTime = Stats->FinishTime;
		Entry->bLeader    = Entry->Position == 1;
		Entry->Gap        = FMath::Max(0.0f, Stats->FinishTime - LeaderTime);
	}

	// Остальные — по текущим позициям; «встают на место» сами, когда финишируют
	for (ABoatBase* Boat : Standings)
	{
		if (!IsValid(Boat) || Finished.ContainsByPredicate([Boat](const FRaceBoatStats* S) { return S->Boat == Boat; }))
		{
			continue;
		}

		const FRaceBoatStats* Stats = Race->BoatStats.FindByPredicate([Boat](const FRaceBoatStats& S) { return S.Boat == Boat; });
		FRaceResultEntry* Entry = MakeEntry(Boat, Stats);
		Entry->State       = Race->bRaceFinished ? ERaceResultState::DNF
		                   : (Boat->IsDead() ? ERaceResultState::Wrecked : ERaceResultState::OnTrack);
		Entry->Lap         = FMath::Clamp(Boat->CurrentLap + 1, 1, FMath::Max(Race->LapsToWin, 1));
		Entry->LapProgress = TrackLength > 0.0f ? Boat->SplineDistance / TrackLength : 0.0f;
	}

	// Разделитель над строкой: не у первой, не у игрока и не у строки сразу под ним (как в макете)
	for (int32 Index = 0; Index < OutEntries.Num(); ++Index)
	{
		OutEntries[Index].bHideDivider = Index == 0 || OutEntries[Index].bIsLocalPlayer || OutEntries[Index - 1].bIsLocalPlayer;
	}
}

// =====================================================================
// ЖИЗНЬ ВИДЖЕТА
// =====================================================================

void URaceResultsWidget::NativeOnInitialized()
{
	Super::NativeOnInitialized();
	SetIsFocusable(true);
}

void URaceResultsWidget::NativeConstruct()
{
	Super::NativeConstruct();

	if (bTakeInputFocus)
	{
		if (APlayerController* PC = GetOwningPlayer())
		{
			FInputModeGameAndUI Mode;
			Mode.SetWidgetToFocus(TakeWidget());
			Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
			Mode.SetHideCursorDuringCapture(false);
			PC->SetInputMode(Mode);
		}
	}

	// Строки-образцы из вёрстки (для вида в Designer) — не настоящие данные
	if (RowContainer)
	{
		RowContainer->ClearChildren();
	}

	if (ARaceGameState* Race = ARaceGameState::GetRaceGameState(this))
	{
		Race->OnRaceStatsChanged.AddUniqueDynamic(this, &URaceResultsWidget::HandleStatsChanged);
		BoundRace = Race;
	}

	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(UpdateTimer, this, &URaceResultsWidget::Refresh,
			1.0f / FMath::Max(UpdateRateHz, 1.0f), true);
	}
	Refresh();
}

void URaceResultsWidget::NativeDestruct()
{
	if (ARaceGameState* Race = BoundRace.Get())
	{
		Race->OnRaceStatsChanged.RemoveDynamic(this, &URaceResultsWidget::HandleStatsChanged);
	}
	BoundRace.Reset();

	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(UpdateTimer);
	}

	if (bTakeInputFocus)
	{
		if (APlayerController* PC = GetOwningPlayer())
		{
			PC->SetInputMode(FInputModeGameOnly());
		}
	}

	Super::NativeDestruct();
}

FReply URaceResultsWidget::NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent)
{
	if (!InKeyEvent.IsRepeat() && ContinueKeys.Contains(InKeyEvent.GetKey()))
	{
		RequestContinue();
		return FReply::Handled();
	}
	// Не наше — дальше в игру (Game And UI): пауза и прочий ввод работают как раньше
	return Super::NativeOnKeyDown(InGeometry, InKeyEvent);
}

void URaceResultsWidget::RequestContinue()
{
	// Двойное нажатие не должно дважды грузить уровень
	if (bContinueRequested)
	{
		return;
	}
	bContinueRequested = true;

	BP_OnContinue();
	OnContinueRequested.Broadcast();
}

void URaceResultsWidget::HandleStatsChanged()
{
	Refresh();
}

void URaceResultsWidget::Refresh()
{
	const ARaceGameState* Race = ARaceGameState::GetRaceGameState(this);
	if (!Race)
	{
		return;
	}

	// Клик мышью (гашетка) отдаёт фокус вьюпорту — и Space уходит в игру. Возвращаем фокус экрану
	if (bTakeInputFocus && !HasAnyUserFocus())
	{
		SetKeyboardFocus();
	}

	TArray<FRaceResultEntry> Entries;
	BuildEntries(this, GetOwningPlayerPawn(), Entries);

	RefreshHeader(Race, Entries);
	RefreshClose(Race);
	RefreshRows(Entries);
}

// =====================================================================
// ОТРИСОВКА
// =====================================================================

void URaceResultsWidget::RefreshHeader(const ARaceGameState* Race, const TArray<FRaceResultEntry>& Entries)
{
	if (TrackTitle)
	{
		const FText TrackName = Race->TrackRoad ? Race->TrackRoad->TrackDisplayName : FText::GetEmpty();
		const FText Laps = FText::AsNumber(Race->LapsToWin);
		TrackTitle->SetText(TrackName.IsEmpty() ? FText::Format(LapsOnlyFormat, Laps) : FText::Format(TrackTitleFormat, TrackName, Laps));
	}

	const FRaceResultEntry* Own = Entries.FindByPredicate([](const FRaceResultEntry& E) { return E.bIsLocalPlayer; });
	SetText(PlaceOf, FText::Format(PlaceOfFormat, FText::AsNumber(Entries.Num())));

	if (!Own)
	{
		SetText(PlaceNum, EmptyText);
		SetText(PlaceSuffix, FText::GetEmpty());
		if (PlaceDelta)
		{
			PlaceDelta->SetVisibility(ESlateVisibility::Collapsed);
		}
		return;
	}

	SetText(PlaceNum, FText::AsNumber(Own->Position));
	SetText(PlaceSuffix, FText::FromString(OrdinalSuffix(Own->Position)));

	FRaceBoatStats Stats;
	const bool bHasStats = Race->GetBoatStats(Own->Boat, Stats);

	// Изменение места за финальный круг: место на его старте минус место финиша
	if (PlaceDelta)
	{
		const int32 Delta = (bHasStats && Stats.FinishPosition > 0 && Stats.FinalLapStartPosition > 0)
			? Stats.FinalLapStartPosition - Stats.FinishPosition : 0;
		PlaceDelta->SetVisibility(Delta != 0 ? ESlateVisibility::SelfHitTestInvisible : ESlateVisibility::Collapsed);
		if (Delta != 0)
		{
			const FLinearColor Color = Delta > 0 ? DeltaGainColor : DeltaLossColor;
			if (DeltaIcon)
			{
				DeltaIcon->SetColorAndOpacity(Color);
				// Одна иконка T_Ico_Up на оба случая — вниз её разворачиваем
				DeltaIcon->SetRenderTransformAngle(Delta > 0 ? 0.0f : 180.0f);
			}
			if (DeltaText)
			{
				DeltaText->SetText(FText::Format(DeltaFormat, FText::AsNumber(FMath::Abs(Delta))));
				DeltaText->SetColorAndOpacity(FSlateColor(Color));
			}
		}
	}

	// Your race
	SetText(StatTime, URaceResultRowWidget::FormatRaceTime(Own->FinishTime, EmptyText));
	SetText(StatBestLap, URaceResultRowWidget::FormatRaceTime(Own->BestLapTime, EmptyText));
	SetText(StatSpeed, bHasStats ? FText::AsNumber(FMath::RoundToInt(Stats.TopSpeedKmh)) : EmptyText);
	SetText(StatKills, FText::AsNumber(bHasStats ? Stats.Kills : 0));
	SetText(StatDamage, FText::FromString(FormatThousands(bHasStats ? FMath::RoundToInt(Stats.DamageDealt) : 0)));
	SetText(StatWrecked, FText::AsNumber(bHasStats ? Stats.Deaths : 0));
}

void URaceResultsWidget::RefreshClose(const ARaceGameState* Race)
{
	const float Remaining = Race->GetRaceCloseRemaining();
	if (Close)
	{
		Close->SetVisibility(Remaining >= 0.0f ? ESlateVisibility::SelfHitTestInvisible : ESlateVisibility::Collapsed);
	}
	if (Remaining < 0.0f)
	{
		return;
	}

	// Вверх до секунды: «0:01» держится до самого закрытия, а не «0:00» последнюю секунду
	const int32 Seconds = FMath::CeilToInt(Remaining);
	SetText(CloseTime, FText::FromString(FString::Printf(TEXT("%d:%02d"), Seconds / 60, Seconds % 60)));

	if (CloseBar)
	{
		if (UMaterialInstanceDynamic* MID = CloseBar->GetDynamicMaterial())
		{
			const float Total = Race->CloseDelayAfterPlayerFinish;
			MID->SetScalarParameterValue(TEXT("Fill"), Total > 0.0f ? FMath::Clamp(Remaining / Total, 0.0f, 1.0f) : 0.0f);
		}
	}
}

void URaceResultsWidget::RefreshRows(const TArray<FRaceResultEntry>& Entries)
{
	if (!RowContainer)
	{
		return;
	}
	if (!RowClass)
	{
		UE_LOG(LogTemp, Warning, TEXT("RaceResultsWidget: RowClass не назначен в Class Defaults"));
		return;
	}

	// Строка i показывает место i — порядок в панели не меняется, меняется только содержимое
	for (int32 Index = 0; Index < Entries.Num(); ++Index)
	{
		if (!Rows.IsValidIndex(Index))
		{
			Rows.Add(CreateWidget<URaceResultRowWidget>(this, RowClass));
		}
		URaceResultRowWidget* Row = Rows[Index];
		if (!Row)
		{
			continue;
		}
		if (Row->GetParent() != RowContainer)
		{
			RowContainer->AddChild(Row);
		}
		Row->ApplyEntry(Entries[Index]);
	}

	// Лодок стало меньше (удалили с уровня) — лишние строки из панели убрать; держит их Rows
	for (int32 Index = Entries.Num(); Index < Rows.Num(); ++Index)
	{
		if (Rows[Index])
		{
			Rows[Index]->RemoveFromParent();
		}
	}
}
