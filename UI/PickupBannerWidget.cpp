#include "UI/PickupBannerWidget.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "Engine/Texture2D.h"
#include "GAS/PickupFeedbackData.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace BannerParams
{
	// Контракт с M_UI_Chevron (SourceArt/UI/HUD/HUD_UE57_Kit/Materials/M_UI_Chevron.hlsl)
	const FName Size(TEXT("Size"));     // фактический размер Image, px — иначе скос и полосы плывут
	const FName Color(TEXT("Color"));   // обводка, заливка и полосы
}

void UPickupBannerWidget::NativeConstruct()
{
	Super::NativeConstruct();

	SetVisibility(ESlateVisibility::HitTestInvisible);
	if (Banner)
	{
		Banner->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (Plate && !PlateMID)
	{
		PlateMID = Plate->GetDynamicMaterial();
	}
}

void UPickupBannerWidget::Show(const UPickupFeedbackData* Feedback)
{
	if (!Feedback || !Banner || !Title)
	{
		return;
	}

	const FSlateColor Color(Feedback->BannerColor);
	Title->SetText(Feedback->BannerTitle);
	if (Value)
	{
		Value->SetText(Feedback->BannerValue);
		Value->SetColorAndOpacity(Color);
		Value->SetVisibility(Feedback->BannerValue.IsEmpty() ? ESlateVisibility::Collapsed : ESlateVisibility::HitTestInvisible);
	}
	if (Icon)
	{
		if (Feedback->BannerIcon)
		{
			// false — размер Image из вёрстки (26 px), а не размер текстуры (52 px, ×2 для чёткости)
			Icon->SetBrushFromTexture(Feedback->BannerIcon, false);
			Icon->SetColorAndOpacity(Feedback->BannerColor);
			Icon->SetVisibility(ESlateVisibility::HitTestInvisible);
		}
		else
		{
			Icon->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
	if (PlateMID)
	{
		PlateMID->SetVectorParameterValue(BannerParams::Color, Feedback->BannerColor);
	}

	Age = 0.0f;
	Banner->SetVisibility(ESlateVisibility::HitTestInvisible);
	Banner->SetRenderOpacity(0.0f);
}

void UPickupBannerWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	if (Age < 0.0f || !Banner)
	{
		return;
	}
	Age += InDeltaTime;

	// Вход: слева +60 px, ease-out; держится; уход: вправо +60 px (ease-in), α → 0 — доска «Шеврон»
	float Offset  = 0.0f;
	float Opacity = 1.0f;
	if (Age < EnterTime)
	{
		const float Q    = 1.0f - FMath::Pow(1.0f - Age / EnterTime, 3.0f);
		Offset  = -SlideDistance * (1.0f - Q);
		Opacity = Q;
	}
	else if (Age >= EnterTime + HoldTime)
	{
		const float Q = (Age - EnterTime - HoldTime) / ExitTime;
		if (Q >= 1.0f)
		{
			Age = -1.0f;
			Banner->SetVisibility(ESlateVisibility::Collapsed);
			return;
		}
		Offset  = SlideDistance * Q * Q;
		Opacity = 1.0f - Q;
	}
	Banner->SetRenderTranslation(FVector2D(Offset, 0.0f));
	Banner->SetRenderOpacity(Opacity);

	// Ширина плашки зависит от текста — размер для материала берём с фактической геометрии каждый кадр.
	// В первый кадр после показа геометрии ещё нет (была Collapsed) — пропускаем, плашка в этот кадр прозрачна
	if (PlateMID && Plate)
	{
		const FVector2D Size = Plate->GetCachedGeometry().GetLocalSize();
		if (Size.X > 1.0 && Size.Y > 1.0)
		{
			PlateMID->SetVectorParameterValue(BannerParams::Size, FLinearColor(Size.X, Size.Y, 0.0f, 0.0f));
		}
	}
}
