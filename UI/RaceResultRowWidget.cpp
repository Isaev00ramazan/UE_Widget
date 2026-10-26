#include "UI/RaceResultRowWidget.h"
#include "Components/Image.h"
#include "Components/RetainerBox.h"
#include "Components/TextBlock.h"
#include "Materials/MaterialInstanceDynamic.h"

void URaceResultRowWidget::NativeOnInitialized()
{
	Super::NativeOnInitialized();

	if (NameText)
	{
		BaseNameFont = NameText->GetFont();
	}
	if (GapText)
	{
		BaseGapFont = GapText->GetFont();
	}
}

FText URaceResultRowWidget::FormatRaceTime(float Seconds, const FText& Empty)
{
	if (Seconds <= 0.0f)
	{
		return Empty;
	}
	const int32 TotalMs = FMath::RoundToInt(Seconds * 1000.0f);
	return FText::FromString(FString::Printf(TEXT("%d:%02d.%03d"), TotalMs / 60000, (TotalMs / 1000) % 60, TotalMs % 1000));
}

void URaceResultRowWidget::SetVisible(UWidget* Widget, bool bVisible)
{
	if (Widget)
	{
		Widget->SetVisibility(bVisible ? ESlateVisibility::SelfHitTestInvisible : ESlateVisibility::Collapsed);
	}
}

void URaceResultRowWidget::SetText(UTextBlock* Text, const FText& Value, const FLinearColor& Color)
{
	if (Text)
	{
		Text->SetText(Value);
		Text->SetColorAndOpacity(FSlateColor(Color));
	}
}

void URaceResultRowWidget::ApplyEntry(const FRaceResultEntry& Entry)
{
	const bool bYou      = Entry.bIsLocalPlayer;
	const bool bFinished = Entry.State == ERaceResultState::Finished;
	const bool bLive     = Entry.State == ERaceResultState::OnTrack || Entry.State == ERaceResultState::Wrecked;

	// Подложка игрока: градиент + полоса слева + тег YOU
	SetVisible(RowBg, bYou);
	SetVisible(YouStripe, bYou);
	SetVisible(YouTag, bYou);
	SetVisible(Divider, !Entry.bHideDivider);

	// Номер: 1-е — combat со свечением, 2–3 — ink, дальше muted; у игрока — его цвет поверх всего
	FLinearColor PosColor = Entry.Position == 1 ? ColorFirst : (Entry.Position <= 3 ? ColorInk : ColorMuted);
	if (bYou)
	{
		PosColor = ColorPlayer;
	}
	SetText(PosText, FText::AsNumber(Entry.Position), PosColor);
	if (PosGlow)
	{
		// Retainer рисует сцену в свою текстуру — держать его включённым на всех строках незачем
		PosGlow->SetRetainRendering(Entry.Position == 1);
	}

	if (NameText)
	{
		FSlateFontInfo Font = BaseNameFont;
		if (bYou)
		{
			Font.TypefaceFontName = PlayerNameTypeface;
		}
		NameText->SetFont(Font);
	}
	SetText(NameText, Entry.Name, bYou ? ColorPlayer : (bLive ? ColorMuted : ColorInk));

	// Время или живой прогресс
	SetVisible(TimeText, !bLive);
	SetVisible(LiveBox, bLive);
	if (bFinished)
	{
		SetText(TimeText, FormatRaceTime(Entry.FinishTime, EmptyText), ColorInk);
	}
	else if (Entry.State == ERaceResultState::DNF)
	{
		SetText(TimeText, DNFText, ColorMuted);
	}
	if (bLive)
	{
		const bool bWrecked = Entry.State == ERaceResultState::Wrecked;
		SetText(LiveStatus, bWrecked ? WreckedText : OnTrackText, bWrecked ? ColorWrecked : ColorRace);
		SetText(LiveLap, FText::Format(LapFormat, FText::AsNumber(Entry.Lap), FText::AsNumber(Entry.LapsTotal)), ColorMuted);
		if (LiveBar)
		{
			if (UMaterialInstanceDynamic* MID = LiveBar->GetDynamicMaterial())
			{
				MID->SetScalarParameterValue(TEXT("Fill"), FMath::Clamp(Entry.LapProgress, 0.0f, 1.0f));
				MID->SetVectorParameterValue(TEXT("OnColor"), bWrecked ? ColorFaint : ColorRace);
			}
		}
	}

	// Отрыв: «LEADER» у первого — подпись другим шрифтом; у недоехавших — «—»
	if (GapText)
	{
		FSlateFontInfo Font = BaseGapFont;
		if (bFinished && Entry.bLeader)
		{
			Font.TypefaceFontName = LeaderTypeface;
			Font.Size             = LeaderFontSize;
			Font.LetterSpacing    = LeaderLetterSpacing;
			GapText->SetFont(Font);
			SetText(GapText, LeaderText, ColorFirst);
		}
		else
		{
			GapText->SetFont(Font);
			if (bFinished)
			{
				SetText(GapText, FText::FromString(FString::Printf(TEXT("+%.3f"), Entry.Gap)), ColorMuted);
			}
			else
			{
				SetText(GapText, EmptyText, ColorFaint);
			}
		}
	}

	SetText(BestText, FormatRaceTime(Entry.BestLapTime, EmptyText), bYou ? ColorInk : ColorMuted);
	SetVisible(FastestTag, Entry.bFastestLap);
	SetText(KillsText, FText::AsNumber(Entry.Kills), bLive ? ColorMuted : ColorInk);

	BP_OnEntryApplied(Entry);
}
