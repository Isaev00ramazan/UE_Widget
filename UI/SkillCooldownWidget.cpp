#include "UI/SkillCooldownWidget.h"
#include "AbilitySystemComponent.h"
#include "GameplayEffect.h"

void USkillCooldownWidget::InitCooldown(UAbilitySystemComponent* InASC, FGameplayTag InCooldownTag)
{
	if (!IsValid(InASC) || !InCooldownTag.IsValid())
	{
		return;
	}

	if (UAbilitySystemComponent* OldASC = TrackedASC.Get())
	{
		OldASC->OnActiveGameplayEffectAddedDelegateToSelf.Remove(DelegateAdded);
	}

	TrackedASC = InASC;
	CooldownTag = InCooldownTag;
	ClearCooldown();

	// 1. Подписываемся на добавление новых GE
	DelegateAdded = InASC->OnActiveGameplayEffectAddedDelegateToSelf.AddUObject(
		this, &USkillCooldownWidget::OnGEAdded);

	// 2. Ищем, не наложен ли кулдаун ПРЯМО СЕЙЧАС (если UI загрузился позже)
	float MaxRemaining = -1.f;
	FActiveGameplayEffectHandle LongestHandle;
	float LongestDuration = 0.f;

	const FGameplayEffectQuery EmptyQuery; // Пустой запрос = все активные эффекты
	TArray<FActiveGameplayEffectHandle> ExistingHandles = InASC->GetActiveEffects(EmptyQuery);
	
	for (const FActiveGameplayEffectHandle& Handle : ExistingHandles)
	{
		const FActiveGameplayEffect* ActiveGE = InASC->GetActiveGameplayEffect(Handle);
		if (ActiveGE)
		{
			FGameplayTagContainer GrantedTags;
			ActiveGE->Spec.GetAllGrantedTags(GrantedTags);
			
			// Если эффект содержит НАШ тег кулдауна
			if (GrantedTags.HasTag(CooldownTag))
			{
				float Remaining = ActiveGE->GetTimeRemaining(GetWorld()->GetTimeSeconds());
				// Ищем самый долгий (бывает что накидывают 2 кулдауна, нужен больший)
				if (Remaining > MaxRemaining)
				{
					MaxRemaining = Remaining;
					LongestHandle = Handle;
					LongestDuration = ActiveGE->Spec.GetDuration();
				}
			}
		}
	}

	// Если нашли активный кулдаун прямо при старте — активируем виджет
	if (LongestHandle.IsValid() && MaxRemaining > 0.f)
	{
		StartCooldown(LongestHandle, LongestDuration);
	}
	else
	{
		// Иначе сообщаем Blueprint что способность готова к использованию
		BP_OnCooldownFinished();
	}
}

void USkillCooldownWidget::NativeDestruct()
{
	if (UAbilitySystemComponent* ASC = TrackedASC.Get())
	{
		ASC->OnActiveGameplayEffectAddedDelegateToSelf.Remove(DelegateAdded);
	}
	DelegateAdded.Reset();
	
	Super::NativeDestruct();
}

void USkillCooldownWidget::OnGEAdded(UAbilitySystemComponent* ASC, const FGameplayEffectSpec& Spec, FActiveGameplayEffectHandle Handle)
{
	// Эффект наложен — проверяем теги
	FGameplayTagContainer GrantedTags;
	Spec.GetAllGrantedTags(GrantedTags);
	
	if (GrantedTags.HasTag(CooldownTag))
	{
		StartCooldown(Handle, Spec.GetDuration());
	}
}

void USkillCooldownWidget::StartCooldown(FActiveGameplayEffectHandle Handle, float InDuration)
{
	ActiveHandle = Handle;
	Duration = FMath::Max(InDuration, 0.01f);
	bIsOnCooldown = true;

	// Подписываемся на снятие ТОЛЬКО ЭТОГО конкретного эффекта
	if (UAbilitySystemComponent* ASC = TrackedASC.Get())
	{
		if (FOnActiveGameplayEffectRemoved_Info* RemoveDel = ASC->OnGameplayEffectRemoved_InfoDelegate(Handle))
		{
			RemoveDel->AddUObject(this, &USkillCooldownWidget::OnGERemoved);
		}
	}

	BP_OnCooldownStarted(Duration);
}

void USkillCooldownWidget::OnGERemoved(const FGameplayEffectRemovalInfo& RemovalInfo)
{
	// Сняли эффект — если это НАШ кулдаун, то очищаем
	if (RemovalInfo.ActiveEffect && RemovalInfo.ActiveEffect->Handle == ActiveHandle)
	{
		ClearCooldown();
	}
}

void USkillCooldownWidget::ClearCooldown()
{
	// Если уже выключен — игнорируем
	if (!bIsOnCooldown) return;
	
	bIsOnCooldown = false;
	ActiveHandle.Invalidate();
	
	BP_OnCooldownFinished();
}

void USkillCooldownWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	// Тик работает только когда мы В кулдауне
	if (!bIsOnCooldown)
	{
		return;
	}

	UAbilitySystemComponent* ASC = TrackedASC.Get();
	if (!IsValid(ASC) || !ActiveHandle.IsValid())
	{
		ClearCooldown(); // Ошибка связи, сброс
		return;
	}

	const FActiveGameplayEffect* ActiveGE = ASC->GetActiveGameplayEffect(ActiveHandle);
	if (!ActiveGE)
	{
		ClearCooldown(); // Эффект исчез
		return;
	}

	// Получаем реальное оставшееся время
	float Remaining = ActiveGE->GetTimeRemaining(GetWorld()->GetTimeSeconds());
	
	// Если время истекло
	if (Remaining <= 0.f)
	{
		// C++ сам вызовет OnGERemoved, но на всякий случай шлем 0.0
		BP_OnCooldownTick(0.f, 0.f);
		return;
	}

	// Посылаем процент 1.0 (только началось) -> 0.0 (заканчивается)
	const float Percent = FMath::Clamp(Remaining / Duration, 0.f, 1.f);
	BP_OnCooldownTick(Percent, Remaining);
}
