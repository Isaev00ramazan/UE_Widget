#include "UI/HUDMotion.h"
#include "GameFramework/Actor.h"

namespace HUDMotionPrivate
{
	constexpr float Gravity    = 980.665f;   // см/с²
	constexpr float MaxInputG  = 4.0f;       // удар о стену даёт десятки g за кадр — HUD не должен улетать
	constexpr float SubStepDt  = 1.0f / 240.0f;
}

void FHUDMotionState::Step(const FHUDMotionSettings& S, const AActor* Boat, float Dt)
{
	using namespace HUDMotionPrivate;
	if (Dt <= KINDA_SMALL_NUMBER)
	{
		return;
	}

	float Target[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
	if (Boat)
	{
		// Сигналы — как в UBoatCameraFeelComponent: рыскание по приращению угла, ускорение по разности скоростей
		const FVector Velocity = Boat->GetVelocity();
		const float   Yaw      = Boat->GetActorRotation().Yaw;
		if (!bPrimed)
		{
			PrevYaw      = Yaw;
			PrevVelocity = Velocity;
			bPrimed      = true;
		}
		const float   RawYawRate = FMath::FindDeltaAngleDegrees(PrevYaw, Yaw) / Dt;
		const FVector Accel      = (Velocity - PrevVelocity) / Dt / Gravity;
		PrevYaw      = Yaw;
		PrevVelocity = Velocity;

		const FRotationMatrix Axes(FRotator(0.0f, Yaw, 0.0f));
		const float RawLat  = FMath::Clamp(static_cast<float>(FVector::DotProduct(Accel, Axes.GetUnitAxis(EAxis::Y))), -MaxInputG, MaxInputG);
		const float RawFwd  = FMath::Clamp(static_cast<float>(FVector::DotProduct(Accel, Axes.GetUnitAxis(EAxis::X))), -MaxInputG, MaxInputG);
		const float RawVert = static_cast<float>(Velocity.Z) / 100.0f;

		const float A = S.InputSmoothing > KINDA_SMALL_NUMBER ? 1.0f - FMath::Exp(-Dt / S.InputSmoothing) : 1.0f;
		YawRate   = FMath::Lerp(YawRate, RawYawRate, A);
		LateralG  = FMath::Lerp(LateralG, RawLat, A);
		ForwardG  = FMath::Lerp(ForwardG, RawFwd, A);
		VertSpeed = FMath::Lerp(VertSpeed, RawVert, A);

		const float SpeedKmh = static_cast<float>(Velocity.Size2D()) * 0.036f;
		const float Sf = S.FullEffectSpeed > KINDA_SMALL_NUMBER ? FMath::Clamp(SpeedKmh / S.FullEffectSpeed, 0.0f, 1.0f) : 1.0f;

		// Правый поворот: YawRate > 0, LateralG > 0. «Против поворота» / «наружу» — влево, то есть X < 0
		Target[0] = FMath::Clamp(-(S.ShiftPerYawRate * YawRate + S.ShiftPerLateralG * LateralG) * Sf, -S.MaxShiftX, S.MaxShiftX);
		Target[1] = FMath::Clamp((S.SinkPerForwardG * ForwardG + S.BobPerVerticalSpeed * VertSpeed) * Sf, -S.MaxShiftY, S.MaxShiftY);
		Target[2] = FMath::Clamp(-S.RollPerYawRate * YawRate * Sf, -S.MaxRoll, S.MaxRoll);
		Target[3] = FMath::Clamp(-S.ScalePerForwardG * ForwardG * Sf, -S.MaxScaleDelta, S.MaxScaleDelta);
	}
	else
	{
		bPrimed = false;
	}

	// Пружина с затуханием на каждый канал; мелкие подшаги — устойчиво на любом FPS и при жёсткой пружине
	const float W = 2.0f * PI * S.SpringFrequency;
	const int32 Steps = FMath::Clamp(FMath::CeilToInt(Dt / SubStepDt), 1, 32);
	const float H = Dt / Steps;
	for (int32 Step = 0; Step < Steps; ++Step)
	{
		for (int32 C = 0; C < 4; ++C)
		{
			Vel[C] += (W * W * (Target[C] - Pos[C]) - 2.0f * S.SpringDamping * W * Vel[C]) * H;
			Pos[C] += Vel[C] * H;
		}
	}
}
