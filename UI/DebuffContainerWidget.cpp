#include "UI/DebuffContainerWidget.h"
#include "UI/BuffIconWidget.h"
#include "AbilitySystemComponent.h"
#include "GameplayEffect.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "AbilitySystemGlobals.h"
#include "GameFramework/PlayerController.h"
#include "Async/Async.h"

void UDebuffContainerWidget::NativeConstruct()
{
	Super::NativeConstruct();

	if (!bAutoBindToPlayer)
	{
		return;
	}

	// Лодка меняется (возрождение, гараж) — следим за контроллером, а не берём пешку один раз
	if (APlayerController* PC = GetOwningPlayer())
	{
		PC->OnPossessedPawnChanged.AddUniqueDynamic(this, &UDebuffContainerWidget::HandlePossessedPawnChanged);
		BindToPawn(PC->GetPawn());
	}
}

void UDebuffContainerWidget::HandlePossessedPawnChanged(APawn* OldPawn, APawn* NewPawn)
{
	BindToPawn(NewPawn);
}

void UDebuffContainerWidget::BindToPawn(APawn* Pawn)
{
	if (UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Pawn))
	{
		InitWithASC(ASC);
	}
	else
	{
		CleanupDelegates();
		ClearAllIcons();
		TrackedASC.Reset();
	}
}

void UDebuffContainerWidget::InitWithASC(UAbilitySystemComponent* InASC)
{
	if (!IsValid(InASC))
	{
		UE_LOG(LogTemp, Warning, TEXT("DebuffContainerWidget::InitWithASC — передан невалидный ASC"));
		return;
	}

	CleanupDelegates();
	ClearAllIcons(); // бейджи прошлой лодки
	TrackedASC = InASC;

	// ── Подписаться на добавление GE ──
	DelegateAdded = InASC->OnActiveGameplayEffectAddedDelegateToSelf.AddUObject(
		this, &UDebuffContainerWidget::OnGEAdded);

	// ── Синхронизировать уже активные эффекты (если HUD создан после их применения) ──
	// GetActiveEffects с пустым Query возвращает все активные хэндлы
	const FGameplayEffectQuery EmptyQuery;
	TArray<FActiveGameplayEffectHandle> ExistingHandles = InASC->GetActiveEffects(EmptyQuery);
	for (const FActiveGameplayEffectHandle& ExistingHandle : ExistingHandles)
	{
		const FActiveGameplayEffect* ActiveGE = InASC->GetActiveGameplayEffect(ExistingHandle);
		if (ActiveGE && ShouldShowEffect(ActiveGE->Spec))
		{
			OnGEAdded(InASC, ActiveGE->Spec, ExistingHandle);
		}
	}
}

void UDebuffContainerWidget::NativeDestruct()
{
	if (APlayerController* PC = GetOwningPlayer())
	{
		PC->OnPossessedPawnChanged.RemoveDynamic(this, &UDebuffContainerWidget::HandlePossessedPawnChanged);
	}
	CleanupDelegates();
	Super::NativeDestruct();
}

void UDebuffContainerWidget::OnGEAdded(UAbilitySystemComponent* ASC,
                                        const FGameplayEffectSpec& Spec,
                                        FActiveGameplayEffectHandle Handle)
{
	// Эффект могли применить с физпотока (BP Async Tick) — виджеты создавать можно только на игровом.
	// Переносим, перечитав эффект по хэндлу: Spec по ссылке к тому моменту уже недействителен.
	if (!IsInGameThread())
	{
		AsyncTask(ENamedThreads::GameThread,
			[WeakThis = TWeakObjectPtr<UDebuffContainerWidget>(this), WeakASC = TWeakObjectPtr<UAbilitySystemComponent>(ASC), Handle]()
			{
				UDebuffContainerWidget* Container = WeakThis.Get();
				UAbilitySystemComponent* LiveASC  = WeakASC.Get();
				const FActiveGameplayEffect* ActiveGE = LiveASC ? LiveASC->GetActiveGameplayEffect(Handle) : nullptr;
				if (Container && ActiveGE)
				{
					Container->OnGEAdded(LiveASC, ActiveGE->Spec, Handle);
				}
			});
		return;
	}

	if (!ShouldShowEffect(Spec))
	{
		return;
	}

	// Не создавать дубликат если хэндл уже отслеживается
	if (ActiveIcons.Contains(Handle))
	{
		return;
	}

	if (!IsValid(IconWidgetClass))
	{
		UE_LOG(LogTemp, Warning, TEXT("DebuffContainerWidget: IconWidgetClass не назначен в Blueprint!"));
		return;
	}

	UBuffIconWidget* Icon = CreateWidget<UBuffIconWidget>(this, IconWidgetClass);
	if (!IsValid(Icon))
	{
		return;
	}

	// Иконку берём из SetByCaller или передаём nullptr если нет (в BP настроишь)
	const float Duration = Spec.GetDuration();

	Icon->Setup(ASC, Handle, Duration, /*InIcon=*/nullptr);

	FGameplayTagContainer GrantedTags;
	Spec.GetAllGrantedTags(GrantedTags);
	if (const FHUDDebuffStyle* Style = FindStyle(GrantedTags))
	{
		FText Name = Style->Name;
		if (Name.IsEmpty())
		{
			// «Boat.State.Debuff.Slowed» → «Slowed» (в бейдже To Upper)
			FString Leaf = Style->Tag.ToString();
			int32 Dot = INDEX_NONE;
			if (Leaf.FindLastChar(TEXT('.'), Dot))
			{
				Leaf.RightChopInline(Dot + 1);
			}
			Name = FText::FromString(Leaf);
		}

		// Силу бейдж читает сам и обновляет на лету (ApplyStackingDebuff меняет её на месте)
		Icon->ApplyStyle(*Style, Name);
	}

	if (IsValid(DebuffBox))
	{
		if (UHorizontalBoxSlot* BoxSlot = DebuffBox->AddChildToHorizontalBox(Icon))
		{
			BoxSlot->SetPadding(FMargin(0.0f, 0.0f, BadgeSpacing, 0.0f));
		}
	}

	ActiveIcons.Add(Handle, Icon);

	// ── Подписаться на удаление ЭТОГО конкретного эффекта (per-handle) ──
	// Это правильный API UE5: делегат привязан к одному Handle
	if (FOnActiveGameplayEffectRemoved_Info* RemoveDelegate = ASC->OnGameplayEffectRemoved_InfoDelegate(Handle))
	{
		RemoveDelegate->AddUObject(this, &UDebuffContainerWidget::OnGERemoved);
	}

	BP_OnDebuffAdded(Icon);
}

void UDebuffContainerWidget::OnGERemoved(const FGameplayEffectRemovalInfo& RemovalInfo)
{
	if (!RemovalInfo.ActiveEffect)
	{
		return;
	}
	const FActiveGameplayEffectHandle Handle = RemovalInfo.ActiveEffect->Handle;

	if (!IsInGameThread())
	{
		AsyncTask(ENamedThreads::GameThread, [WeakThis = TWeakObjectPtr<UDebuffContainerWidget>(this), Handle]()
		{
			if (UDebuffContainerWidget* Container = WeakThis.Get())
			{
				Container->RemoveIcon(Handle);
			}
		});
		return;
	}

	RemoveIcon(Handle);
}

void UDebuffContainerWidget::RemoveIcon(FActiveGameplayEffectHandle Handle)
{
	TObjectPtr<UBuffIconWidget>* FoundIcon = ActiveIcons.Find(Handle);
	if (!FoundIcon)
	{
		return;
	}
	if (IsValid(*FoundIcon))
	{
		(*FoundIcon)->RemoveFromParent();
	}

	ActiveIcons.Remove(Handle);
	BP_OnDebuffRemoved(Handle);
}

void UDebuffContainerWidget::ClearAllIcons()
{
	for (const TPair<FActiveGameplayEffectHandle, TObjectPtr<UBuffIconWidget>>& Pair : ActiveIcons)
	{
		if (IsValid(Pair.Value))
		{
			Pair.Value->RemoveFromParent();
		}
	}
	ActiveIcons.Reset();
}

const FHUDDebuffStyle* UDebuffContainerWidget::FindStyle(const FGameplayTagContainer& GrantedTags) const
{
	// ⚠️ Стили — из CDO класса, а не из экземпляра. Экземпляр внутри другого виджета (WBP_CombatDock) хранит
	// свою копию массива с момента, когда его туда положили, и правки Class Defaults до неё не доходили:
	// в игре был Scale 1 без Multiplier при 100 и ✓ в классе (2026-10-05). EditDefaultsOnly — сбросить её негде.
	const UDebuffContainerWidget* Defaults = GetClass()->GetDefaultObject<UDebuffContainerWidget>();
	const TArray<FHUDDebuffStyle>& ActiveStyles = Defaults ? Defaults->Styles : Styles;

	for (const FHUDDebuffStyle& Style : ActiveStyles)
	{
		if (Style.Tag.IsValid() && GrantedTags.HasTag(Style.Tag))
		{
			return &Style;
		}
	}
	return nullptr;
}

bool UDebuffContainerWidget::ShouldShowEffect(const FGameplayEffectSpec& Spec) const
{
	// Instant-эффекты не имеют иконки (срабатывают и исчезают мгновенно)
	if (Spec.GetDuration() <= 0.f)
	{
		return false;
	}

	// Если фильтр не задан — показывать все HasDuration эффекты
	if (FilterTags.IsEmpty())
	{
		return true;
	}

	// Проверить, что хотя бы один тег фильтра присутствует в эффекте
	FGameplayTagContainer GrantedTags;
	Spec.GetAllGrantedTags(GrantedTags);
	return GrantedTags.HasAny(FilterTags);
}

void UDebuffContainerWidget::CleanupDelegates()
{
	if (UAbilitySystemComponent* ASC = TrackedASC.Get())
	{
		ASC->OnActiveGameplayEffectAddedDelegateToSelf.Remove(DelegateAdded);
		// Per-handle делегаты на удаление очищаются автоматически вместе с GE
	}
	DelegateAdded.Reset();
}
