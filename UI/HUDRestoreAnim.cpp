#include "UI/HUDRestoreAnim.h"
#include "UI/VM_BoatStatus.h"
#include "Blueprint/UserWidget.h"
#include "Components/Image.h"
#include "Engine/GameInstance.h"
#include "MVVMGameSubsystem.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Types/MVVMViewModelCollection.h"
#include "Types/MVVMViewModelContext.h"

namespace HUDRestoreAnim
{
	const FName Fill(TEXT("Fill"));
	const FName Segments(TEXT("Segments"));
	const FName GainFrom(TEXT("GainFrom"));
	const FName GainColor(TEXT("GainColor"));
	const FName GainHeadColor(TEXT("GainHeadColor"));
	const FName GapFlash(TEXT("GapFlash"));
	const FName GlowColor(TEXT("GlowColor"));
	const FName GlowFalloff(TEXT("GlowFalloff"));
	const FName InnerGlowPx(TEXT("InnerGlowPx"));
	const FName InnerGlowColor(TEXT("InnerGlowColor"));

	UVM_BoatStatus* FindBoatStatus(const UUserWidget* Widget)
	{
		const UGameInstance* GI = Widget ? Widget->GetGameInstance() : nullptr;
		UMVVMGameSubsystem* MVVM = GI ? GI->GetSubsystem<UMVVMGameSubsystem>() : nullptr;
		UMVVMViewModelCollectionObject* Collection = MVVM ? MVVM->GetViewModelCollection() : nullptr;
		if (!Collection)
		{
			return nullptr;
		}
		FMVVMViewModelContext Context;
		Context.ContextClass = UVM_BoatStatus::StaticClass();
		Context.ContextName  = UVM_BoatStatus::CollectionName;
		return Cast<UVM_BoatStatus>(Collection->FindViewModelInstance(Context));
	}

	UMaterialInstanceDynamic* GetMID(UImage* Image)
	{
		return Image ? Image->GetDynamicMaterial() : nullptr;
	}

	float ChipAlpha(float Age, float Hold, float Fade)
	{
		if (Age < 0.0f)
		{
			return 0.0f;
		}
		if (Age < 0.1f)
		{
			return Age / 0.1f;
		}
		return Age < Hold ? 1.0f : FMath::Clamp(1.0f - (Age - Hold) / Fade, 0.0f, 1.0f);
	}
}
