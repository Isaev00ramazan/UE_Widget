#include "UI/VM_Weapons.h"
#include "GAS/AWeaponBase.h"

const FName UVM_Weapons::CollectionName(TEXT("Weapons"));

// Поменять FText-поле, только если изменилось содержимое (см. TextDiffers)
#define VMW_SET_TEXT(Member, NewText) \
	if (TextDiffers(Member, NewText)) { UE_MVVM_SET_PROPERTY_VALUE(Member, NewText); }

bool UVM_Weapons::TextDiffers(const FText& Current, const FText& New)
{
	return !Current.IdenticalTo(New) && !Current.ToString().Equals(New.ToString(), ESearchCase::CaseSensitive);
}

void UVM_Weapons::SetLight(const AAWeaponBase* Weapon, const FText& Name)
{
	UE_MVVM_SET_PROPERTY_VALUE(bHasLight, Weapon != nullptr);
	if (!Weapon)
	{
		return;
	}

	VMW_SET_TEXT(LightName, Name);
	UE_MVVM_SET_PROPERTY_VALUE(LightIcon, Weapon->WeaponIcon);

	const FText Ammo = Weapon->bInfiniteAmmo
		? FText::FromString(TEXT("∞"))
		: FText::AsNumber(Weapon->CurrentAmmo);
	VMW_SET_TEXT(LightAmmoText, Ammo);
}

void UVM_Weapons::SetMain(const AAWeaponBase* Weapon, const FText& Name, float ReloadHintFraction)
{
	UE_MVVM_SET_PROPERTY_VALUE(bHasMain, Weapon != nullptr);
	if (!Weapon)
	{
		return;
	}

	VMW_SET_TEXT(MainName, Name);
	UE_MVVM_SET_PROPERTY_VALUE(MainIcon, Weapon->WeaponIcon);

	const int32 Magazine = FMath::Max(Weapon->MagazineSize, 1);
	const int32 Current  = Weapon->CurrentAmmo;
	const int32 Reserve  = Weapon->ReserveAmmo;
	const int32 Total    = Current + Reserve;

	// Порядок важен: идущая перезарядка важнее подсказки; EMPTY — только когда кончилось всё.
	// LOW по общему запасу не показываем — решение по дизайну (2026-10-04).
	EHUDWeaponState State = EHUDWeaponState::Normal;
	if (Weapon->bInfiniteAmmo)
	{
		State = EHUDWeaponState::Normal;
	}
	else if (Weapon->IsReloading())
	{
		State = EHUDWeaponState::Reloading;
	}
	else if (Total <= 0)
	{
		State = EHUDWeaponState::Empty;
	}
	else if (Reserve > 0 && Current <= FMath::FloorToInt(Magazine * ReloadHintFraction))
	{
		// Магазин на 2 торпеды: floor(0.5) = 0 — подсказка только на пустом магазине
		State = EHUDWeaponState::NeedReload;
	}
	UE_MVVM_SET_PROPERTY_VALUE(MainState, State);

	int32 Shown    = Current;
	float Progress = 0.0f;
	float Pips     = 0.0f;

	if (State == EHUDWeaponState::Reloading)
	{
		Progress = Weapon->GetReloadProgress();
		Pips     = Progress; // пипсы заполняются вместе с перезарядкой, частичный — жёлтый (EdgeColor)
		// Пока перезарядка не кончилась — в магазине столько, сколько есть (0), а не «сколько будет»:
		// патроны переходят из запаса в магазин только в OnReloadFinished (решение 2026-10-07)

		// Остаток округляем вверх до десятых: «0.0s», пока перезарядка ещё идёт, не показываем.
		// Printf, а не FText::AsNumber: в русской культуре вышло бы «1,9s», в макете — точка
		const float Tenths = FMath::CeilToFloat(Weapon->GetReloadTimeRemaining() * 10.0f) / 10.0f;
		VMW_SET_TEXT(ReloadTimeText, FText::FromString(FString::Printf(TEXT("%.1fs"), Tenths)));
	}
	else
	{
		// Доля магазина без округления: материал сам делит её на пипсы, частичный пустеет сверху вниз
		Pips = FMath::Clamp(static_cast<float>(Current) / Magazine, 0.0f, 1.0f);
	}

	if (!FMath::IsNearlyEqual(PipsFill, Pips, 0.001f))
	{
		UE_MVVM_SET_PROPERTY_VALUE(PipsFill, Pips);
	}

	// Полоска 224 px: шаг 0.002 меньше пикселя — чаще будить виджет незачем
	if (!FMath::IsNearlyEqual(ReloadProgress, Progress, 0.002f))
	{
		UE_MVVM_SET_PROPERTY_VALUE(ReloadProgress, Progress);
	}

	if (Weapon->bInfiniteAmmo)
	{
		VMW_SET_TEXT(MainAmmoText, FText::FromString(TEXT("∞")));
		VMW_SET_TEXT(MainReserveText, FText::GetEmpty());
	}
	else
	{
		VMW_SET_TEXT(MainAmmoText, FText::AsNumber(Shown));
		VMW_SET_TEXT(MainReserveText, FText::Format(INVTEXT("/{0}"), FText::AsNumber(Reserve)));
	}
}

void UVM_Weapons::SetNext(const AAWeaponBase* Weapon, const FText& Name)
{
	UE_MVVM_SET_PROPERTY_VALUE(bHasNext, Weapon != nullptr);
	if (!Weapon)
	{
		return;
	}

	VMW_SET_TEXT(NextName, Name);
	const FText Ammo = Weapon->bInfiniteAmmo
		? FText::FromString(TEXT("∞"))
		: FText::Format(INVTEXT("{0}/{1}"), FText::AsNumber(Weapon->CurrentAmmo), FText::AsNumber(Weapon->ReserveAmmo));
	VMW_SET_TEXT(NextAmmoText, Ammo);
}

#undef VMW_SET_TEXT
