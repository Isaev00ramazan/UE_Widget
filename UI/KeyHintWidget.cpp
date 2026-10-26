#include "UI/KeyHintWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "CommonInputBaseTypes.h"
#include "CommonInputSubsystem.h"
#include "Engine/LocalPlayer.h"
#include "EnhancedInputSubsystems.h"
#include "InputAction.h"

UKeyHintWidget::UKeyHintWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	MissingKeyText = INVTEXT("?");

	// Подписи под Xbox. Стрелки крестовины — словами: в F_HUD может не быть глифов ↑↓←→
	KeyLabels.Add(EKeys::Gamepad_FaceButton_Bottom,  INVTEXT("A"));
	KeyLabels.Add(EKeys::Gamepad_FaceButton_Right,   INVTEXT("B"));
	KeyLabels.Add(EKeys::Gamepad_FaceButton_Left,    INVTEXT("X"));
	KeyLabels.Add(EKeys::Gamepad_FaceButton_Top,     INVTEXT("Y"));
	KeyLabels.Add(EKeys::Gamepad_LeftShoulder,       INVTEXT("LB"));
	KeyLabels.Add(EKeys::Gamepad_RightShoulder,      INVTEXT("RB"));
	KeyLabels.Add(EKeys::Gamepad_LeftTrigger,        INVTEXT("LT"));
	KeyLabels.Add(EKeys::Gamepad_RightTrigger,       INVTEXT("RT"));
	KeyLabels.Add(EKeys::Gamepad_LeftTriggerAxis,    INVTEXT("LT"));
	KeyLabels.Add(EKeys::Gamepad_RightTriggerAxis,   INVTEXT("RT"));
	KeyLabels.Add(EKeys::Gamepad_LeftThumbstick,     INVTEXT("LS"));
	KeyLabels.Add(EKeys::Gamepad_RightThumbstick,    INVTEXT("RS"));
	KeyLabels.Add(EKeys::Gamepad_Left2D,             INVTEXT("LS"));
	KeyLabels.Add(EKeys::Gamepad_LeftX,              INVTEXT("LS"));
	KeyLabels.Add(EKeys::Gamepad_LeftY,              INVTEXT("LS"));
	KeyLabels.Add(EKeys::Gamepad_LeftStick_Up,       INVTEXT("LS"));
	KeyLabels.Add(EKeys::Gamepad_LeftStick_Down,     INVTEXT("LS"));
	KeyLabels.Add(EKeys::Gamepad_LeftStick_Left,     INVTEXT("LS"));
	KeyLabels.Add(EKeys::Gamepad_LeftStick_Right,    INVTEXT("LS"));
	KeyLabels.Add(EKeys::Gamepad_Right2D,            INVTEXT("RS"));
	KeyLabels.Add(EKeys::Gamepad_RightX,             INVTEXT("RS"));
	KeyLabels.Add(EKeys::Gamepad_RightY,             INVTEXT("RS"));
	KeyLabels.Add(EKeys::Gamepad_RightStick_Up,      INVTEXT("RS"));
	KeyLabels.Add(EKeys::Gamepad_RightStick_Down,    INVTEXT("RS"));
	KeyLabels.Add(EKeys::Gamepad_RightStick_Left,    INVTEXT("RS"));
	KeyLabels.Add(EKeys::Gamepad_RightStick_Right,   INVTEXT("RS"));
	KeyLabels.Add(EKeys::Gamepad_DPad_Up,            INVTEXT("D-UP"));
	KeyLabels.Add(EKeys::Gamepad_DPad_Down,          INVTEXT("D-DOWN"));
	KeyLabels.Add(EKeys::Gamepad_DPad_Left,          INVTEXT("D-LEFT"));
	KeyLabels.Add(EKeys::Gamepad_DPad_Right,         INVTEXT("D-RIGHT"));
	KeyLabels.Add(EKeys::Gamepad_Special_Left,       INVTEXT("VIEW"));
	KeyLabels.Add(EKeys::Gamepad_Special_Right,      INVTEXT("MENU"));

	// Клавиатура и мышь — одним словом: движок пишет «Left Shift», «Space Bar», «Left Mouse Button»,
	// на клавише-подсказке это не помещается. Левая/правая не различаются — игроку это не нужно.
	KeyLabels.Add(EKeys::LeftShift,                  INVTEXT("Shift"));
	KeyLabels.Add(EKeys::RightShift,                 INVTEXT("Shift"));
	KeyLabels.Add(EKeys::LeftControl,                INVTEXT("Ctrl"));
	KeyLabels.Add(EKeys::RightControl,               INVTEXT("Ctrl"));
	KeyLabels.Add(EKeys::LeftAlt,                    INVTEXT("Alt"));
	KeyLabels.Add(EKeys::RightAlt,                   INVTEXT("Alt"));
	KeyLabels.Add(EKeys::SpaceBar,                   INVTEXT("Space"));
	KeyLabels.Add(EKeys::Enter,                      INVTEXT("Enter"));
	KeyLabels.Add(EKeys::Escape,                     INVTEXT("Esc"));
	KeyLabels.Add(EKeys::BackSpace,                  INVTEXT("Backspace"));
	KeyLabels.Add(EKeys::CapsLock,                   INVTEXT("Caps"));
	KeyLabels.Add(EKeys::PageUp,                     INVTEXT("PgUp"));
	KeyLabels.Add(EKeys::PageDown,                   INVTEXT("PgDn"));
	KeyLabels.Add(EKeys::LeftMouseButton,            INVTEXT("LMB"));
	KeyLabels.Add(EKeys::RightMouseButton,           INVTEXT("RMB"));
	KeyLabels.Add(EKeys::MiddleMouseButton,          INVTEXT("MMB"));
	KeyLabels.Add(EKeys::MouseScrollUp,              INVTEXT("Wheel"));
	KeyLabels.Add(EKeys::MouseScrollDown,            INVTEXT("Wheel"));
	KeyLabels.Add(EKeys::MouseWheelAxis,             INVTEXT("Wheel"));
	KeyLabels.Add(EKeys::ThumbMouseButton,           INVTEXT("Mouse4"));
	KeyLabels.Add(EKeys::ThumbMouseButton2,          INVTEXT("Mouse5"));
}

void UKeyHintWidget::NativeConstruct()
{
	Super::NativeConstruct();

	ULocalPlayer* LocalPlayer = GetOwningLocalPlayer();
	if (!LocalPlayer)
	{
		return;
	}

	// Устройство — из CommonInput, а не из UMadInputSubsystem: у того автоопределение вырезано, bIsGamepad сам
	// не меняется. CommonInput в проекте уже настроен (меню паузы) и переключается по последнему нажатию.
	if (UCommonInputSubsystem* CommonInput = UCommonInputSubsystem::Get(LocalPlayer))
	{
		CommonInputSubsystem     = CommonInput;
		InputMethodChangedHandle = CommonInput->OnInputMethodChangedNative.AddUObject(this, &UKeyHintWidget::HandleInputMethodChanged);
	}

	// Пересборка маппингов — это и «IMC добавили позже виджета» (HUD создаётся раньше BeginPlay лодки),
	// и смена пресета IMC, и переназначение клавиш игроком.
	if (UEnhancedInputLocalPlayerSubsystem* EnhancedInput = LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
	{
		EnhancedInputSubsystem = EnhancedInput;
		EnhancedInput->ControlMappingsRebuiltDelegate.AddUniqueDynamic(this, &UKeyHintWidget::HandleControlMappingsRebuilt);
	}

	RefreshKeyHint();
}

void UKeyHintWidget::NativeDestruct()
{
	// ⚠️ Отписка обязательна: подсистемы живут дольше виджета (рестарт уровня, закрытие меню)
	if (UCommonInputSubsystem* CommonInput = CommonInputSubsystem.Get())
	{
		CommonInput->OnInputMethodChangedNative.Remove(InputMethodChangedHandle);
	}
	InputMethodChangedHandle.Reset();

	if (UEnhancedInputLocalPlayerSubsystem* EnhancedInput = EnhancedInputSubsystem.Get())
	{
		EnhancedInput->ControlMappingsRebuiltDelegate.RemoveDynamic(this, &UKeyHintWidget::HandleControlMappingsRebuilt);
	}

	CommonInputSubsystem.Reset();
	EnhancedInputSubsystem.Reset();

	Super::NativeDestruct();
}

void UKeyHintWidget::HandleInputMethodChanged(ECommonInputType NewInputType)
{
	RefreshKeyHint();
}

void UKeyHintWidget::HandleControlMappingsRebuilt()
{
	RefreshKeyHint();
}

UTextBlock* UKeyHintWidget::ResolveTextBlock()
{
	if (KeyText)
	{
		return KeyText;
	}

	if (!FallbackTextBlock && WidgetTree)
	{
		WidgetTree->ForEachWidget([this](UWidget* Widget)
		{
			if (!FallbackTextBlock)
			{
				FallbackTextBlock = Cast<UTextBlock>(Widget);
			}
		});
	}
	return FallbackTextBlock;
}

void UKeyHintWidget::RefreshKeyHint()
{
	if (!InputAction)
	{
		return;
	}

	const UCommonInputSubsystem* CommonInput = CommonInputSubsystem.Get();
	const ECommonInputType InputType = CommonInput ? CommonInput->GetCurrentInputType() : ECommonInputType::MouseAndKeyboard;
	const bool bGamepad = (InputType == ECommonInputType::Gamepad);

	// Клавиши текущего устройства по порядку маппинга. Одна клавиша может прийти из нескольких активных
	// контекстов — без AddUnique KeyIndex считал бы её дважды.
	TArray<FKey> DeviceKeys;
	if (const UEnhancedInputLocalPlayerSubsystem* EnhancedInput = EnhancedInputSubsystem.Get())
	{
		for (const FKey& Key : EnhancedInput->QueryKeysMappedToAction(InputAction))
		{
			if (Key.IsValid() && !Key.IsTouch() && Key.IsGamepadKey() == bGamepad)
			{
				DeviceKeys.AddUnique(Key);
			}
		}
	}

	DisplayedKey    = DeviceKeys.IsValidIndex(KeyIndex) ? DeviceKeys[KeyIndex] : FKey();
	bShowingGamepad = bGamepad;

	FText Label = MissingKeyText;
	if (DisplayedKey.IsValid())
	{
		const FText* CustomLabel = KeyLabels.Find(DisplayedKey);
		Label = CustomLabel ? *CustomLabel : DisplayedKey.GetDisplayName(false);
	}

	// Иконка — только если её попросили и в виджете есть KeyIcon; иначе видимость текста не трогаем,
	// чтобы не ломать вёрстку WBP, который просто переподчинили этому классу
	bool bIconShown = false;
	if (bUseIcons && KeyIcon)
	{
		FSlateBrush Brush;
		const UCommonInputPlatformSettings* PlatformSettings = UCommonInputPlatformSettings::Get();
		const FName GamepadName = CommonInput ? CommonInput->GetCurrentGamepadName() : NAME_None;
		bIconShown = DisplayedKey.IsValid() && PlatformSettings
			&& PlatformSettings->TryGetInputBrush(Brush, DisplayedKey, InputType, GamepadName);

		if (bIconShown)
		{
			KeyIcon->SetBrush(Brush);
		}
		KeyIcon->SetVisibility(bIconShown ? ESlateVisibility::SelfHitTestInvisible : ESlateVisibility::Collapsed);
	}

	if (UTextBlock* TextBlock = ResolveTextBlock())
	{
		TextBlock->SetText(Label);
		if (bUseIcons && KeyIcon)
		{
			TextBlock->SetVisibility(bIconShown ? ESlateVisibility::Collapsed : ESlateVisibility::SelfHitTestInvisible);
		}
	}

	BP_OnKeyHintChanged(DisplayedKey, Label, bGamepad);
}
