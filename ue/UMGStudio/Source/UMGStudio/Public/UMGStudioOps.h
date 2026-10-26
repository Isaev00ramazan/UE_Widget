// UMG Studio: операции над Widget Blueprint — залить дерево из текста буфера UMG, выгрузить дерево обратно.
#pragma once

#include "CoreMinimal.h"

struct FUMGStudioImportOptions
{
	/** Пакет ассета: /Game/UI/HUD/Widgets/WBP_X */
	FString AssetPath;
	/** Текст буфера UMG (как Ctrl+C в Designer / *.paste.txt) — корень станет корнем WidgetTree */
	FString Text;
	/** Родитель (C++-база): /Script/MadWater.HUDDriveWidget; пусто — не трогать (у нового — UserWidget) */
	FString ParentClass;
	/** FillScreen | Custom | CustomOnScreen | Desired | DesiredOnScreen; пусто — не трогать */
	FString DesignSizeMode;
	FVector2D DesignSize = FVector2D::ZeroVector;
	/** Резервная копия .uasset в Saved/UMGStudio/Backups перед записью */
	bool bBackup = true;
	bool bSave = true;
	/** Открыть редактор виджета после записи */
	bool bOpenEditor = false;
};

struct FUMGStudioImportResult
{
	bool bOk = false;
	bool bCreated = false;
	FString Error;
	FString Backup;
	FString Root;
	int32 Widgets = 0;
	int32 CompileErrors = 0;
	int32 CompileWarnings = 0;
	/** Сообщения компилятора и предупреждения импорта */
	TArray<FString> Messages;
	/** Имена, которые UE переименовал при вставке (BindWidget их не найдёт) */
	TArray<FString> Renamed;
};

namespace UMGStudio
{
	FUMGStudioImportResult ImportWidgetText(const FUMGStudioImportOptions& Options);

	/** Дерево WBP целиком в формате буфера UMG (как Ctrl+C корня в Hierarchy). false — нет ассета. */
	bool ExportWidgetText(const FString& AssetPath, FString& OutText, FString& OutError);

	bool OpenWidgetEditor(const FString& AssetPath);
}
