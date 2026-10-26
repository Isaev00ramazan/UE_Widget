// Те же операции из Python / Editor Utility: unreal.UMGStudioLibrary.import_widget_text(...)
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "UMGStudioLibrary.generated.h"

UCLASS()
class UUMGStudioLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Залить дерево WBP из текста буфера UMG (создаст WBP, если его нет). Возвращает true без ошибок компиляции.
	 * @param AssetPath   /Game/UI/HUD/Widgets/WBP_X
	 * @param ParentClass пусто — не менять; /Script/Модуль.Класс — C++-база
	 * @param DesignSizeMode пусто | FillScreen | Custom | CustomOnScreen | Desired | DesiredOnScreen
	 */
	UFUNCTION(BlueprintCallable, Category = "UMG Studio")
	static bool ImportWidgetText(const FString& AssetPath, const FString& Text, const FString& ParentClass,
		const FString& DesignSizeMode, FVector2D DesignSize, FString& OutReport);

	/** Дерево WBP в формате буфера UMG (как Ctrl+C корня в Hierarchy) */
	UFUNCTION(BlueprintCallable, Category = "UMG Studio")
	static bool ExportWidgetText(const FString& AssetPath, FString& OutText);
};
