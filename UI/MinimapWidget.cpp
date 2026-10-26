#include "UI/MinimapWidget.h"
#include "UI/MinimapIconWidget.h"
#include "UI/MinimapSubsystem.h"
#include "Boat/BoatBase.h"
#include "GAS/BFL_CPP.h"
#include "Race/RaceGameState.h"
#include "SplineRoad.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/Image.h"
#include "Components/SplineComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "EngineUtils.h"
#include "TimerManager.h"

void UMinimapWidget::InitMinimap(USplineComponent* InSpline, float InTrackWidth)
{
	if (!IsValid(InSpline))
	{
		UE_LOG(LogTemp, Warning, TEXT("MinimapWidget::InitMinimap — передан невалидный Spline"));
		return;
	}

	TrackWorldBounds = UBFL_CPP::ComputeTrackWorldBounds(InSpline, InTrackWidth, SampleStep, EdgePaddingPercent);
	bBoundsReady = true;

	// Радар обновляется в NativeTick — таймер ему не нужен
	if (bRadarMode)
	{
		return;
	}

	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(
			UpdateTimerHandle, this, &UMinimapWidget::UpdateIcons,
			1.0f / FMath::Max(UpdateRateHz, 1.0f), true);
	}
}

void UMinimapWidget::NativeDestruct()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(UpdateTimerHandle);
	}

	Super::NativeDestruct();
}

void UMinimapWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	if (bRadarMode)
	{
		UpdateRadar();
	}
}

bool UMinimapWidget::TryAutoInit()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return false;
	}

	// Трасса матча, иначе — первая на уровне (тестовые уровни без GameMode гонки)
	ASplineRoad* Road = nullptr;
	if (const ARaceGameState* Race = ARaceGameState::GetRaceGameState(this))
	{
		Road = Race->TrackRoad;
	}
	if (!Road)
	{
		TActorIterator<ASplineRoad> It(World);
		Road = It ? *It : nullptr;
	}
	if (!Road || !Road->SplineComponent)
	{
		return false;
	}

	InitMinimap(Road->SplineComponent, Road->TrackWidth);
	return bBoundsReady;
}

void UMinimapWidget::SyncIcons(const TArray<ABoatBase*>& ActiveBoats)
{
	// Убираем иконки лодок, которых больше нет в реестре (умерли/покинули игру)
	for (auto It = ActiveIcons.CreateIterator(); It; ++It)
	{
		ABoatBase* Boat = It.Key().Get();
		if (!Boat || !ActiveBoats.Contains(Boat))
		{
			if (UMinimapIconWidget* Icon = It.Value())
			{
				Icon->RemoveFromParent();
			}
			It.RemoveCurrent();
		}
	}

	if (!IsValid(IconWidgetClass))
	{
		UE_LOG(LogTemp, Warning, TEXT("MinimapWidget: IconWidgetClass не назначен в Blueprint!"));
		return;
	}

	for (ABoatBase* Boat : ActiveBoats)
	{
		if (!IsValid(Boat))
		{
			continue;
		}

		TObjectPtr<UMinimapIconWidget>& Icon = ActiveIcons.FindOrAdd(Boat);
		if (Icon)
		{
			continue;
		}

		Icon = CreateWidget<UMinimapIconWidget>(this, IconWidgetClass);
		if (!Icon)
		{
			continue;
		}

		Icon->Setup(Boat);

		if (UCanvasPanelSlot* NewSlot = IconCanvas->AddChildToCanvas(Icon))
		{
			NewSlot->SetAnchors(FAnchors(0.f, 0.f));
			NewSlot->SetAlignment(FVector2D(0.5f, 0.5f));
			// Радар: слот по размеру метки, иначе центр метки — центр слота 100 × 30 по умолчанию.
			// Старую карту не трогаем — её иконки настроены под прежний слот.
			NewSlot->SetAutoSize(bRadarMode);
		}

		BP_OnIconAdded(Icon);
	}
}

void UMinimapWidget::UpdateIcons()
{
	if (!IsValid(IconCanvas))
	{
		return;
	}

	UWorld* World = GetWorld();
	UMinimapSubsystem* Subsystem = World ? World->GetSubsystem<UMinimapSubsystem>() : nullptr;
	if (!Subsystem)
	{
		return;
	}

	const TArray<ABoatBase*> ActiveBoats = Subsystem->GetActiveBoats();
	SyncIcons(ActiveBoats);

	for (ABoatBase* Boat : ActiveBoats)
	{
		UMinimapIconWidget* Icon = IsValid(Boat) ? ActiveIcons.FindRef(Boat).Get() : nullptr;
		if (!Icon)
		{
			continue;
		}

		const FVector2D PixelPos = UBFL_CPP::WorldLocationToMinimapPixel(Boat->GetActorLocation(), TrackWorldBounds, MapPixelSize);

		if (UCanvasPanelSlot* IconSlot = Cast<UCanvasPanelSlot>(Icon->Slot))
		{
			IconSlot->SetPosition(PixelPos);
		}

		// Курс лодки в мировых XY -> угол на карте. IconRotationOffsetDegrees компенсирует
		// собственный поворот карты (Render Transform на IconCanvas/Image).
		const FVector Forward = Boat->GetBoatForwardDirection();
		const float WorldAngleDeg = FMath::RadiansToDegrees(FMath::Atan2(Forward.Y, Forward.X));
		Icon->SetRenderTransformAngle(WorldAngleDeg + IconRotationOffsetDegrees);
	}
}

// ============================================================================
// РАДАР
// ============================================================================
//
// Система координат — пиксели карты (WorldLocationToMinimapPixel с MapPixelSize): тот же
// равномерный масштаб, что при запекании, без поворотов и отражений. Материал берёт карту в
// точке Player + R(Yaw) * (смещение от центра / радиус) * Zoom. Метки — обратным преобразованием:
// смещение от игрока на карте → R(−Yaw) → доля радиуса → пиксели канвы.
// ⚠️ Карта (RenderTarget запекания) должна быть квадратной: Zoom в материале одинаков по U и V.

void UMinimapWidget::UpdateRadar()
{
	if (!IsValid(IconCanvas) || (!bBoundsReady && !TryAutoInit()))
	{
		return;
	}

	const ABoatBase* Player = Cast<ABoatBase>(GetOwningPlayerPawn());
	if (!Player)
	{
		return;
	}

	const FVector2D MapPx   = MapPixelSize;
	const FVector2D PlayerPx = UBFL_CPP::WorldLocationToMinimapPixel(Player->GetActorLocation(), TrackWorldBounds, MapPx);

	// Курс на карте = Forward.XY (масштаб равномерный). Yaw такой, что «верх» радара (0, −1)
	// поворачивается в курс: R(Yaw)·(0,−1) = (sin Yaw, −cos Yaw) = Dir
	const FVector Forward = Player->GetBoatForwardDirection();
	const FVector2D Dir = FVector2D(Forward.X, Forward.Y).GetSafeNormal();
	const float Yaw = Dir.IsNearlyZero() ? 0.0f : FMath::Atan2(Dir.X, -Dir.Y);

	if (!RadarMID && RadarBg)
	{
		RadarMID = RadarBg->GetDynamicMaterial();
	}
	if (RadarMID)
	{
		RadarMID->SetVectorParameterValue(TEXT("Player"),
			FLinearColor(PlayerPx.X / FMath::Max(MapPx.X, 1.0), PlayerPx.Y / FMath::Max(MapPx.Y, 1.0), 0.0f, 0.0f));
		RadarMID->SetScalarParameterValue(TEXT("Yaw"), Yaw);
		RadarMID->SetScalarParameterValue(TEXT("Zoom"), RadarZoom);
	}

	UWorld* World = GetWorld();
	UMinimapSubsystem* Subsystem = World ? World->GetSubsystem<UMinimapSubsystem>() : nullptr;
	if (!Subsystem)
	{
		return;
	}

	const TArray<ABoatBase*> ActiveBoats = Subsystem->GetActiveBoats();
	SyncIcons(ActiveBoats);

	const float  PxPerRadius = FMath::Max(RadarZoom * static_cast<float>(MapPx.X), 0.001f); // пикселей карты в радиусе
	const float  Sn = FMath::Sin(Yaw);
	const float  Cs = FMath::Cos(Yaw);
	// R(−Yaw)·v = (v.x·cos + v.y·sin, −v.x·sin + v.y·cos)
	auto ToRadar = [Sn, Cs](const FVector2D& V)
	{
		return FVector2D(V.X * Cs + V.Y * Sn, -V.X * Sn + V.Y * Cs);
	};

	for (ABoatBase* Boat : ActiveBoats)
	{
		UMinimapIconWidget* Icon = IsValid(Boat) ? ActiveIcons.FindRef(Boat).Get() : nullptr;
		if (!Icon)
		{
			continue;
		}

		// Своя лодка — стрелка в центре (PlayerArrow), её метку не показываем
		if (Boat == Player)
		{
			Icon->SetVisibility(ESlateVisibility::Collapsed);
			continue;
		}

		const FVector2D BoatPx = UBFL_CPP::WorldLocationToMinimapPixel(Boat->GetActorLocation(), TrackWorldBounds, MapPx);
		FVector2D N = ToRadar(BoatPx - PlayerPx) / PxPerRadius; // доля радиуса, экранные оси

		const float Len = N.Size();
		if (Len > 1.0f)
		{
			if (!bClampIconsToEdge)
			{
				Icon->SetVisibility(ESlateVisibility::Collapsed);
				continue;
			}
			N /= Len;
		}
		Icon->SetVisibility(ESlateVisibility::HitTestInvisible);

		if (UCanvasPanelSlot* IconSlot = Cast<UCanvasPanelSlot>(Icon->Slot))
		{
			IconSlot->SetPosition(RadarCenterPx + N * RadarRadiusPx);
		}

		// Курс соперника в осях радара: 0° — вправо, по часовой (ось Y канвы вниз)
		const FVector BoatForward = Boat->GetBoatForwardDirection();
		const FVector2D S = ToRadar(FVector2D(BoatForward.X, BoatForward.Y));
		Icon->SetRenderTransformAngle(FMath::RadiansToDegrees(FMath::Atan2(S.Y, S.X)) + IconRotationOffsetDegrees);
	}
}
