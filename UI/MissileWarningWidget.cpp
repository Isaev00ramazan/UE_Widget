#include "UI/MissileWarningWidget.h"
#include "Blueprint/WidgetLayoutLibrary.h"
#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"

namespace MissileWarningUI
{
	// Имена параметров M_UI_WarnArc и M_UI_Panel
	const FName ArcDeg(TEXT("ArcDeg"));
	const FName Width(TEXT("Width"));
	const FName Color(TEXT("Color"));
	const FName Opacity(TEXT("Opacity"));
	const FName Size(TEXT("Size"));
	const FName StrokeColor(TEXT("StrokeColor"));
	const FName InnerGlowColor(TEXT("InnerGlowColor"));

	/** Пульс уровня в момент Now: плавный косинус между PulseMin и 1 или мигание ступенькой */
	float Pulse(const FMissileArcStyle& Style, double Now)
	{
		const float Period = FMath::Max(Style.PulsePeriod, 0.01f);
		const float Phase  = static_cast<float>(FMath::Fmod(Now, static_cast<double>(Period))) / Period;
		if (Style.bBlink)
		{
			return Phase < 0.5f ? 1.0f : Style.PulseMin;
		}
		return FMath::Lerp(Style.PulseMin, 1.0f, 0.5f + 0.5f * FMath::Cos(Phase * 2.0f * PI));
	}
}

void UMissileWarningWidget::NativeOnInitialized()
{
	Super::NativeOnInitialized();

	// Индикатор поверх игры: клики проходят насквозь
	SetVisibility(ESlateVisibility::HitTestInvisible);

	if (ArcTemplate)
	{
		ArcTemplate->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (LabelTemplate)
	{
		LabelTemplate->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (RingRoot)
	{
		RingRoot->SetRenderOpacity(0.0f);
	}
	if (BadgeBg)
	{
		BadgeMaterial = BadgeBg->GetDynamicMaterial();
	}
}

void UMissileWarningWidget::NativeDestruct()
{
	for (FMissileArcVisual& Visual : Visuals)
	{
		if (Visual.Arc)
		{
			Visual.Arc->RemoveFromParent();
		}
		if (Visual.Label)
		{
			Visual.Label->RemoveFromParent();
		}
	}
	Visuals.Reset();

	Super::NativeDestruct();
}

void UMissileWarningWidget::SetWarningComponent(UMissileWarningComponent* InComponent)
{
	Warning = InComponent;
}

UMissileWarningComponent* UMissileWarningWidget::ResolveComponent()
{
	if (!Warning)
	{
		if (const APawn* Pawn = GetOwningPlayerPawn())
		{
			Warning = Pawn->FindComponentByClass<UMissileWarningComponent>();
		}
	}
	return Warning;
}

const FMissileArcStyle& UMissileWarningWidget::StyleFor(EMissileThreatLevel Level) const
{
	switch (Level)
	{
	case EMissileThreatLevel::Imminent: return ImminentStyle;
	case EMissileThreatLevel::Near:     return NearStyle;
	default:                            return FarStyle;
	}
}

void UMissileWarningWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	const UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();

	ResolveComponent();
	SyncVisuals(Now);

	bool bAnyAlive = false;
	for (FMissileArcVisual& Visual : Visuals)
	{
		UpdateVisual(Visual, Now);
		bAnyAlive |= Visual.DeadTime < 0.0;
	}

	// Кольцо и бейдж: появляются при первой угрозе, гаснут, когда угроз нет
	const float Target = bAnyAlive ? 1.0f : 0.0f;
	const float Speed  = 1.0f / FMath::Max(bAnyAlive ? RingFadeInTime : RingFadeOutTime, 0.01f);
	RingAlpha = FMath::FInterpConstantTo(RingAlpha, Target, InDeltaTime, Speed);

	if (RingRoot)
	{
		RingRoot->SetRenderOpacity(RingAlpha);
		RingRoot->SetVisibility(RingAlpha > 0.0f ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}
	if (RingAlpha <= 0.0f)
	{
		return;
	}

	UpdateRingPosition();

	if (Warning && Warning->Threats.Num() > 0)
	{
		UpdateBadge(Warning->ClosestLevel, Warning->Threats.Num());
	}
}

void UMissileWarningWidget::UpdateRingPosition()
{
	UCanvasPanelSlot* RingSlot = RingRoot ? Cast<UCanvasPanelSlot>(RingRoot->Slot) : nullptr;
	APlayerController* PC      = GetOwningPlayer();
	const APawn* Pawn          = GetOwningPlayerPawn();
	if (!RingSlot || !PC || !Pawn)
	{
		return; // остаётся там, где стоит в вёрстке
	}

	FVector2D ScreenPos;
	if (UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, Pawn->GetActorLocation(), ScreenPos, true))
	{
		RingSlot->SetPosition(ScreenPos + BoatScreenOffset);
	}
}

void UMissileWarningWidget::SyncVisuals(double Now)
{
	const TArray<FMissileThreat> Empty;
	const TArray<FMissileThreat>& Threats = Warning ? Warning->Threats : Empty;

	// Живые: обновить по угрозе или пометить ушедшими
	for (FMissileArcVisual& Visual : Visuals)
	{
		if (Visual.DeadTime >= 0.0)
		{
			continue;
		}
		// По номеру угрозы, а не по ракете: в залпе ближайшая ракета меняется, дуга при этом не должна
		// гаснуть и вспыхивать заново
		const FMissileThreat* Threat = Threats.FindByPredicate([&](const FMissileThreat& T) { return T.SalvoId == Visual.SalvoId; });
		if (Threat && IsValid(Threat->Missile))
		{
			Visual.Missile      = Threat->Missile.Get();
			Visual.AngleDeg     = Threat->AngleDeg;
			Visual.TimeToImpact = Threat->TimeToImpact;
			Visual.Level        = Threat->Level;
		}
		else
		{
			Visual.DeadTime = Now;
		}
	}

	// Новые ракеты
	for (const FMissileThreat& Threat : Threats)
	{
		const bool bKnown = Visuals.ContainsByPredicate([&](const FMissileArcVisual& V)
		{
			return V.DeadTime < 0.0 && V.SalvoId == Threat.SalvoId;
		});
		if (!bKnown && RingCanvas && ArcTemplate)
		{
			Visuals.Add(MakeVisual(Threat, Now));
		}
	}

	// Догоревшие — убрать
	for (int32 i = Visuals.Num() - 1; i >= 0; --i)
	{
		const FMissileArcVisual& Visual = Visuals[i];
		if (Visual.DeadTime >= 0.0 && Now - Visual.DeadTime >= ArcFadeOutTime)
		{
			if (Visual.Arc)
			{
				Visual.Arc->RemoveFromParent();
			}
			if (Visual.Label)
			{
				Visual.Label->RemoveFromParent();
			}
			Visuals.RemoveAt(i);
		}
	}
}

FMissileArcVisual UMissileWarningWidget::MakeVisual(const FMissileThreat& Threat, double Now)
{
	FMissileArcVisual Visual;
	Visual.Missile      = Threat.Missile.Get();
	Visual.SalvoId      = Threat.SalvoId;
	Visual.AngleDeg     = Threat.AngleDeg;
	Visual.TimeToImpact = Threat.TimeToImpact;
	Visual.Level        = Threat.Level;
	Visual.BornTime     = Now;

	// Дуга: Image во весь Canvas кольца, материал — копия с образца, поворот вокруг центра
	Visual.Arc = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass());
	Visual.Arc->SetBrush(ArcTemplate->GetBrush());
	Visual.Material = Visual.Arc->GetDynamicMaterial();
	Visual.Arc->SetRenderTransformPivot(FVector2D(0.5f, 0.5f));

	if (UCanvasPanelSlot* ArcSlot = RingCanvas->AddChildToCanvas(Visual.Arc))
	{
		ArcSlot->SetAnchors(FAnchors(0.0f, 0.0f, 1.0f, 1.0f));
		ArcSlot->SetOffsets(FMargin(0.0f));
		ArcSlot->SetZOrder(1);   // под бейджем (у него ZOrder выше в вёрстке)
	}

	// Подпись времени: стиль — с образца, всегда горизонтально, по центру на LabelDistance от центра
	Visual.Label = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
	if (LabelTemplate)
	{
		Visual.Label->SetFont(LabelTemplate->GetFont());
		Visual.Label->SetShadowOffset(LabelTemplate->GetShadowOffset());
		Visual.Label->SetShadowColorAndOpacity(LabelTemplate->GetShadowColorAndOpacity());
	}
	Visual.Label->SetJustification(ETextJustify::Center);

	if (UCanvasPanelSlot* LabelSlot = RingCanvas->AddChildToCanvas(Visual.Label))
	{
		LabelSlot->SetAnchors(FAnchors(0.0f, 0.0f));
		LabelSlot->SetAlignment(FVector2D(0.5f, 0.5f));
		LabelSlot->SetAutoSize(true);
		LabelSlot->SetZOrder(1);
	}

	return Visual;
}

void UMissileWarningWidget::UpdateVisual(FMissileArcVisual& Visual, double Now)
{
	if (!Visual.Arc)
	{
		return;
	}
	const FMissileArcStyle& Style = StyleFor(Visual.Level);

	// Появление: масштаб AppearScale → 1, ease-out
	const float Born  = FMath::Clamp(static_cast<float>(Now - Visual.BornTime) / FMath::Max(AppearTime, 0.01f), 0.0f, 1.0f);
	const float Scale = FMath::Lerp(AppearScale, 1.0f, 1.0f - FMath::Square(1.0f - Born));

	// Уход: 1 → 0 за ArcFadeOutTime
	const float Fade = Visual.DeadTime < 0.0
		? 1.0f
		: 1.0f - FMath::Clamp(static_cast<float>(Now - Visual.DeadTime) / FMath::Max(ArcFadeOutTime, 0.01f), 0.0f, 1.0f);

	const float Opacity = MissileWarningUI::Pulse(Style, Now) * Fade;

	if (Visual.Material)
	{
		Visual.Material->SetScalarParameterValue(MissileWarningUI::ArcDeg, Style.ArcDeg);
		Visual.Material->SetScalarParameterValue(MissileWarningUI::Width, Style.Width);
		Visual.Material->SetVectorParameterValue(MissileWarningUI::Color, Style.Color);
		Visual.Material->SetScalarParameterValue(MissileWarningUI::Opacity, Opacity);
	}
	Visual.Arc->SetRenderTransformAngle(Visual.AngleDeg);
	Visual.Arc->SetRenderScale(FVector2D(Scale, Scale));

	if (Visual.Label)
	{
		const FVector2D Center = RingCanvas ? RingCanvas->GetCachedGeometry().GetLocalSize() * 0.5f : FVector2D(320.0, 320.0);
		const float Rad = FMath::DegreesToRadians(Visual.AngleDeg);
		const FVector2D Pos = Center + FVector2D(FMath::Sin(Rad), -FMath::Cos(Rad)) * LabelDistance;

		if (UCanvasPanelSlot* LabelSlot = Cast<UCanvasPanelSlot>(Visual.Label->Slot))
		{
			LabelSlot->SetPosition(Pos);
		}
		Visual.Label->SetText(FText::FromString(FString::Printf(TEXT("%.1fs"), FMath::Min(Visual.TimeToImpact, 9.9f))));
		Visual.Label->SetColorAndOpacity(FSlateColor(Style.Color));
		Visual.Label->SetRenderOpacity(Opacity);
	}
}

void UMissileWarningWidget::UpdateBadge(EMissileThreatLevel Level, int32 Count)
{
	const FMissileArcStyle& Style = StyleFor(Level);
	const bool bFar = Level == EMissileThreatLevel::Far;

	if (BadgeText)
	{
		BadgeText->SetText(Level == EMissileThreatLevel::Imminent
			? NSLOCTEXT("MissileWarning", "Incoming", "INCOMING")
			: NSLOCTEXT("MissileWarning", "Missile", "MISSILE"));
		BadgeText->SetColorAndOpacity(FSlateColor(Style.Color));
	}
	if (BadgeIcon)
	{
		BadgeIcon->SetColorAndOpacity(Style.Color);
	}
	if (BadgeCount)
	{
		BadgeCount->SetVisibility(Count > 1 ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
		BadgeCount->SetText(FText::FromString(FString::Printf(TEXT("×%d"), Count)));
	}

	if (BadgeMaterial && BadgeBg)
	{
		// M_UI_Panel: Size = фактический размер Image, иначе скосы и рамка плывут (ширина меняется с текстом)
		const FVector2D BgSize = BadgeBg->GetCachedGeometry().GetLocalSize();
		if (BgSize.X > 1.0 && BgSize.Y > 1.0)
		{
			BadgeMaterial->SetVectorParameterValue(MissileWarningUI::Size, FLinearColor(BgSize.X, BgSize.Y, 0.0f, 0.0f));
		}

		FLinearColor Glow = Style.Color;
		Glow.A = bFar ? BadgeGlowAlphaFar : BadgeGlowAlphaNear;
		BadgeMaterial->SetVectorParameterValue(MissileWarningUI::StrokeColor, Style.Color);
		BadgeMaterial->SetVectorParameterValue(MissileWarningUI::InnerGlowColor, Glow);
	}
}
