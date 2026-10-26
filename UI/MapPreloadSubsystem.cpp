#include "UI/MapPreloadSubsystem.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"

DEFINE_LOG_CATEGORY(LogMapPreload);

namespace
{
	int32 GMapPreload = 1;
	FAutoConsoleVariableRef CVarMapPreload(
		TEXT("map.Preload"), GMapPreload,
		TEXT("Предзагрузка следующего уровня меню (UMapPreloadSubsystem): 1 — вкл, 0 — выкл (сравнить в игре)"));

	// Пары «открыт → грузить заранее». Имена — длинные имена пакетов, как их передаёт OpenLevel
	const FName MainMenuMap(TEXT("/Game/ProMainMenuV3/Levels/LVL_MainMenu_HaveLogo"));
	const FName GarageMap(TEXT("/Game/ProMainMenuV3/Levels/LVL_GarageMenu"));

	FName GetNextMap(FName CurrentMap)
	{
		if (CurrentMap == MainMenuMap)
		{
			return GarageMap;
		}
		if (CurrentMap == GarageMap)
		{
			return MainMenuMap;
		}
		return NAME_None;
	}
}

bool UMapPreloadSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	// В редакторе пользы нет (PIE берёт копию мира), а загруженный в фоне мир мешал бы редактору
	if (GIsEditor)
	{
		return false;
	}
	const UGameInstance* GameInstance = Cast<UGameInstance>(Outer);
	return GameInstance && !GameInstance->IsDedicatedServerInstance();
}

void UMapPreloadSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	PreLoadMapHandle  = FCoreUObjectDelegates::PreLoadMap.AddUObject(this, &UMapPreloadSubsystem::HandlePreLoadMap);
	PostLoadMapHandle = FCoreUObjectDelegates::PostLoadMapWithWorld.AddUObject(this, &UMapPreloadSubsystem::HandlePostLoadMap);
}

void UMapPreloadSubsystem::Deinitialize()
{
	FCoreUObjectDelegates::PreLoadMap.Remove(PreLoadMapHandle);
	FCoreUObjectDelegates::PostLoadMapWithWorld.Remove(PostLoadMapHandle);
	Release();

	Super::Deinitialize();
}

void UMapPreloadSubsystem::HandlePreLoadMap(const FString& MapName)
{
	if (PreloadPackageName.IsNone())
	{
		return;
	}

	if (FName(*MapName) != PreloadPackageName)
	{
		// Ушли не туда (меню → гонка): отпускаем заранее, чтобы GC внутри LoadMap освободил память до новой карты.
		// Незаконченную загрузку не дожидаемся — её результат проигнорирует OnPreloadFinished
		UE_LOG(LogMapPreload, Log, TEXT("Переход на %s — предзагрузка %s не пригодилась"), *MapName, *PreloadPackageName.ToString());
		Release();
		return;
	}

	// ⚠️ Пакет ещё грузится — дождаться. Иначе LoadMap найдёт недогруженный пакет и возьмёт его как готовый
	if (PreloadRequestId != INDEX_NONE)
	{
		UE_LOG(LogMapPreload, Log, TEXT("Переход на %s раньше конца предзагрузки — догружаем"), *MapName);
		FlushAsyncLoading(PreloadRequestId);
	}
	else
	{
		UE_LOG(LogMapPreload, Log, TEXT("Переход на %s — уровень уже в памяти"), *MapName);
	}
}

void UMapPreloadSubsystem::HandlePostLoadMap(UWorld* LoadedWorld)
{
	if (!LoadedWorld || LoadedWorld->GetGameInstance() != GetGameInstance())
	{
		return;
	}

	// Мир стал активным и держится движком — наша ссылка больше не нужна (и опасна, см. заголовок)
	Release();

	if (GMapPreload == 0)
	{
		return;
	}

	const FName NextMap = GetNextMap(LoadedWorld->GetPackage()->GetFName());
	if (!NextMap.IsNone())
	{
		StartPreload(NextMap);
	}
}

void UMapPreloadSubsystem::StartPreload(FName PackageName)
{
	if (!FPackageName::DoesPackageExist(PackageName.ToString()))
	{
		UE_LOG(LogMapPreload, Warning, TEXT("Уровень %s не найден — предзагрузка пропущена"), *PackageName.ToString());
		return;
	}

	PreloadPackageName = PackageName;
	PreloadStartTime   = FPlatformTime::Seconds();
	PreloadRequestId   = LoadPackageAsync(PackageName.ToString(),
		FLoadPackageAsyncDelegate::CreateUObject(this, &UMapPreloadSubsystem::OnPreloadFinished));

	UE_LOG(LogMapPreload, Log, TEXT("Предзагрузка %s начата"), *PackageName.ToString());
}

void UMapPreloadSubsystem::OnPreloadFinished(const FName& PackageName, UPackage* Package, EAsyncLoadingResult::Type Result)
{
	// Загрузку уже отменили (Release) или начали другую — результат не наш
	if (PackageName != PreloadPackageName || PreloadRequestId == INDEX_NONE)
	{
		return;
	}
	PreloadRequestId = INDEX_NONE;

	if (Result != EAsyncLoadingResult::Succeeded || !Package)
	{
		UE_LOG(LogMapPreload, Warning, TEXT("Предзагрузка %s не удалась"), *PackageName.ToString());
		PreloadPackageName = NAME_None;
		return;
	}

	PreloadedWorld = UWorld::FindWorldInPackage(Package);
	UE_LOG(LogMapPreload, Log, TEXT("Предзагрузка %s готова за %.2f с"),
		*PackageName.ToString(), FPlatformTime::Seconds() - PreloadStartTime);
}

void UMapPreloadSubsystem::Release()
{
	PreloadedWorld     = nullptr;
	PreloadPackageName = NAME_None;
	PreloadRequestId   = INDEX_NONE;
}
