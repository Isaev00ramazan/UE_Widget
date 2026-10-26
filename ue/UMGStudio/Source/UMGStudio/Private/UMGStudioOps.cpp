#include "UMGStudioOps.h"

#include "AssetToolsModule.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Components/PanelWidget.h"
#include "Components/Widget.h"
#include "Editor.h"
#include "FileHelpers.h"
#include "HAL/FileManager.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/DateTime.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "ScopedTransaction.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "WidgetBlueprint.h"
#include "WidgetBlueprintEditorUtils.h"
#include "WidgetBlueprintFactory.h"

#define LOCTEXT_NAMESPACE "UMGStudio"

namespace
{
	FString AssetNameOf(const FString& AssetPath)
	{
		return FPackageName::GetLongPackageAssetName(AssetPath);
	}

	UWidgetBlueprint* LoadWidgetBlueprint(const FString& AssetPath)
	{
		const FString ObjectPath = AssetPath + TEXT(".") + AssetNameOf(AssetPath);
		return LoadObject<UWidgetBlueprint>(nullptr, *ObjectPath, nullptr, LOAD_NoWarn);
	}

	UClass* FindParentClass(const FString& Path, FString& OutError)
	{
		if (Path.IsEmpty())
		{
			return nullptr;
		}
		UClass* Class = LoadObject<UClass>(nullptr, *Path, nullptr, LOAD_NoWarn);
		if (!Class && !Path.EndsWith(TEXT("_C")) && Path.StartsWith(TEXT("/Game/")))
		{
			// Blueprint-родитель: /Game/.../WBP_Base → /Game/.../WBP_Base.WBP_Base_C
			const FString Name = FPackageName::GetLongPackageAssetName(Path);
			Class = LoadObject<UClass>(nullptr, *(Path + TEXT(".") + Name + TEXT("_C")), nullptr, LOAD_NoWarn);
		}
		if (!Class || !Class->IsChildOf(UUserWidget::StaticClass()))
		{
			OutError = FString::Printf(TEXT("Родитель %s не найден или не наследник UserWidget"), *Path);
			return nullptr;
		}
		return Class;
	}

	UWidgetBlueprint* CreateWidgetBlueprint(const FString& AssetPath, UClass* Parent)
	{
		UWidgetBlueprintFactory* Factory = NewObject<UWidgetBlueprintFactory>();
		Factory->ParentClass = Parent ? Parent : UUserWidget::StaticClass();
		IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools").Get();
		UObject* Asset = AssetTools.CreateAsset(AssetNameOf(AssetPath), FPackageName::GetLongPackagePath(AssetPath),
			UWidgetBlueprint::StaticClass(), Factory);
		return Cast<UWidgetBlueprint>(Asset);
	}

	FString BackupPackage(const FString& AssetPath)
	{
		FString File;
		if (!FPackageName::TryConvertLongPackageNameToFilename(AssetPath, File, FPackageName::GetAssetPackageExtension())
			|| !IFileManager::Get().FileExists(*File))
		{
			return FString();
		}
		const FString Dest = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("UMGStudio"), TEXT("Backups"),
			FString::Printf(TEXT("%s_%s.uasset"), *AssetNameOf(AssetPath), *FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"))));
		return IFileManager::Get().Copy(*Dest, *File) == COPY_OK ? FPaths::ConvertRelativePathToFull(Dest) : FString();
	}

	/** Имена виджетов из текста буфера (верхние Begin Object, кроме WidgetSlotPair) */
	TArray<FString> NamesInText(const FString& Text)
	{
		TArray<FString> Lines, Names;
		Text.ParseIntoArrayLines(Lines, false);
		for (const FString& Line : Lines)
		{
			if (!Line.StartsWith(TEXT("Begin Object ")) || Line.Contains(TEXT("WidgetSlotPair")))
			{
				continue;
			}
			const int32 Start = Line.Find(TEXT("Name=\""));
			if (Start == INDEX_NONE)
			{
				continue;
			}
			const int32 From = Start + 6;
			const int32 End = Line.Find(TEXT("\""), ESearchCase::CaseSensitive, ESearchDir::FromStart, From);
			if (End > From)
			{
				Names.Add(Line.Mid(From, End - From));
			}
		}
		return Names;
	}

	bool SetPropertyByText(UObject* Object, const FName Name, const FString& Value)
	{
		FProperty* Property = Object ? Object->GetClass()->FindPropertyByName(Name) : nullptr;
		if (!Property)
		{
			return false;
		}
		Object->Modify();
		return Property->ImportText_Direct(*Value, Property->ContainerPtrToValuePtr<void>(Object), Object, PPF_None) != nullptr;
	}

	void CollectCompileMessages(const FCompilerResultsLog& Log, FUMGStudioImportResult& Result)
	{
		for (const TSharedRef<FTokenizedMessage>& Message : Log.Messages)
		{
			const EMessageSeverity::Type Severity = Message->GetSeverity();
			const TCHAR* Tag = Severity == EMessageSeverity::Error ? TEXT("Ошибка") :
				Severity == EMessageSeverity::Warning || Severity == EMessageSeverity::PerformanceWarning ? TEXT("Предупреждение") : TEXT("Инфо");
			Result.Messages.Add(FString::Printf(TEXT("%s: %s"), Tag, *Message->ToText().ToString()));
		}
		Result.CompileErrors = Log.NumErrors;
		Result.CompileWarnings = Log.NumWarnings;
	}
}

FUMGStudioImportResult UMGStudio::ImportWidgetText(const FUMGStudioImportOptions& Options)
{
	FUMGStudioImportResult Result;
	if (!FPackageName::IsValidLongPackageName(Options.AssetPath))
	{
		Result.Error = FString::Printf(TEXT("Неверный путь ассета: %s (нужно /Game/.../WBP_X)"), *Options.AssetPath);
		return Result;
	}
	if (Options.Text.IsEmpty())
	{
		Result.Error = TEXT("Пустой текст вставки");
		return Result;
	}
	const TArray<FString> Expected = NamesInText(Options.Text);
	if (Expected.Num() == 0)
	{
		Result.Error = TEXT("В тексте нет виджетов (ожидается формат буфера UMG: Begin Object … End Object)");
		return Result;
	}
	FString Error;
	UClass* Parent = FindParentClass(Options.ParentClass, Error);
	if (!Error.IsEmpty())
	{
		Result.Error = Error;
		return Result;
	}

	UWidgetBlueprint* BP = LoadWidgetBlueprint(Options.AssetPath);
	if (!BP)
	{
		if (FPackageName::DoesPackageExist(Options.AssetPath))
		{
			Result.Error = FString::Printf(TEXT("%s существует, но это не Widget Blueprint"), *Options.AssetPath);
			return Result;
		}
		BP = CreateWidgetBlueprint(Options.AssetPath, Parent);
		if (!BP)
		{
			Result.Error = FString::Printf(TEXT("Не удалось создать %s"), *Options.AssetPath);
			return Result;
		}
		Result.bCreated = true;
	}
	else if (Options.bBackup)
	{
		Result.Backup = BackupPackage(Options.AssetPath);
	}

	// Открытый редактор виджета держит своё превью дерева — закрываем, после записи откроем снова
	UAssetEditorSubsystem* AssetEditors = GEditor ? GEditor->GetEditorSubsystem<UAssetEditorSubsystem>() : nullptr;
	const bool bWasOpen = AssetEditors && AssetEditors->FindEditorForAsset(BP, false) != nullptr;
	if (AssetEditors)
	{
		AssetEditors->CloseAllEditorsForAsset(BP);
	}

	{
		FScopedTransaction Transaction(FText::Format(LOCTEXT("ImportTx", "UMG Studio: {0}"), FText::FromString(AssetNameOf(Options.AssetPath))));
		BP->Modify();
		UWidgetTree* Tree = BP->WidgetTree;
		Tree->Modify();

		// Старое дерево — в Transient (как удаление в Designer), чтобы имена освободились для новых виджетов
		TArray<UWidget*> OldWidgets;
		Tree->GetAllWidgets(OldWidgets);
		TSet<FName> OldNames;
		Tree->RootWidget = nullptr;
		for (UWidget* Widget : OldWidgets)
		{
			OldNames.Add(Widget->GetFName());
			Widget->Modify();
			Widget->Rename(nullptr, GetTransientPackage(), REN_DontCreateRedirectors);
		}

		TSet<UWidget*> Imported;
		TMap<FName, UWidgetSlotPair*> ExtraSlotData;
		FWidgetBlueprintEditorUtils::ImportWidgetsFromText(BP, Options.Text, Imported, ExtraSlotData);

		UWidget* Root = nullptr;
		TSet<FName> NewNames;
		for (UWidget* Widget : Imported)
		{
			NewNames.Add(Widget->GetFName());
			if (Widget->GetParent() == nullptr)
			{
				if (Root)
				{
					Result.Messages.Add(FString::Printf(TEXT("Предупреждение: в тексте несколько корней (%s, %s) — корнем стал первый"),
						*Root->GetName(), *Widget->GetName()));
					continue;
				}
				Root = Widget;
			}
		}
		if (!Root)
		{
			// Откат транзакции возвращает старое дерево на место
			Transaction.Cancel();
			Result.Error = TEXT("Текст не разобрался: ни одного виджета — WBP оставлен как был");
			return Result;
		}
		Tree->RootWidget = Root;
		Result.Root = Root->GetName();
		Result.Widgets = Imported.Num();

		for (const FString& Name : Expected)
		{
			if (!NewNames.Contains(FName(*Name)))
			{
				Result.Renamed.Add(Name);
			}
		}
		// Карта GUID переменных-виджетов (на неё ссылаются графы): ушедшие имена — удалить, новые — добавить
		for (const FName& Name : OldNames)
		{
			if (!NewNames.Contains(Name))
			{
				BP->OnVariableRemoved(Name);
			}
		}
		for (const FName& Name : NewNames)
		{
			if (!OldNames.Contains(Name))
			{
				BP->OnVariableAdded(Name);
			}
		}

		if (Parent && BP->ParentClass != Parent)
		{
			BP->ParentClass = Parent;
			FBlueprintEditorUtils::RefreshAllNodes(BP);
			Result.Messages.Add(FString::Printf(TEXT("Инфо: родитель → %s"), *Parent->GetPathName()));
		}
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
	}

	FCompilerResultsLog CompileLog;
	CompileLog.SetSourcePath(BP->GetPathName());
	FKismetEditorUtilities::CompileBlueprint(BP, EBlueprintCompileOptions::None, &CompileLog);
	CollectCompileMessages(CompileLog, Result);

	// Размер превью в Designer живёт в CDO сгенерированного класса (DesignTimeSize / DesignSizeMode)
	if (!Options.DesignSizeMode.IsEmpty() && BP->GeneratedClass)
	{
		UObject* CDO = BP->GeneratedClass->GetDefaultObject();
		const bool bMode = SetPropertyByText(CDO, TEXT("DesignSizeMode"), Options.DesignSizeMode);
		const bool bSize = Options.DesignSize.X <= 0.0 || SetPropertyByText(CDO, TEXT("DesignTimeSize"),
			FString::Printf(TEXT("(X=%f,Y=%f)"), Options.DesignSize.X, Options.DesignSize.Y));
		if (!bMode || !bSize)
		{
			Result.Messages.Add(TEXT("Предупреждение: размер превью не задан (свойства DesignSizeMode/DesignTimeSize не найдены)"));
		}
		BP->MarkPackageDirty();
	}

	if (Options.bSave)
	{
		UEditorLoadingAndSavingUtils::SavePackages({ BP->GetOutermost() }, false);
	}
	if (AssetEditors && (bWasOpen || Options.bOpenEditor))
	{
		AssetEditors->OpenEditorForAsset(BP);
	}
	for (const FString& Name : Result.Renamed)
	{
		Result.Messages.Add(FString::Printf(TEXT("Предупреждение: %s переименован при вставке — BindWidget его не найдёт"), *Name));
	}
	Result.bOk = Result.CompileErrors == 0;
	if (!Result.bOk)
	{
		Result.Error = FString::Printf(TEXT("Дерево записано, но Blueprint не скомпилировался: ошибок %d"), Result.CompileErrors);
	}
	return Result;
}

bool UMGStudio::ExportWidgetText(const FString& AssetPath, FString& OutText, FString& OutError)
{
	UWidgetBlueprint* BP = LoadWidgetBlueprint(AssetPath);
	if (!BP)
	{
		OutError = FString::Printf(TEXT("Нет Widget Blueprint %s"), *AssetPath);
		return false;
	}
	if (!BP->WidgetTree || !BP->WidgetTree->RootWidget)
	{
		OutError = FString::Printf(TEXT("%s: пустое дерево"), *AssetPath);
		return false;
	}
	TArray<UWidget*> Roots{ BP->WidgetTree->RootWidget };
	FWidgetBlueprintEditorUtils::ExportWidgetsToText(Roots, OutText);
	return true;
}

bool UMGStudio::OpenWidgetEditor(const FString& AssetPath)
{
	UWidgetBlueprint* BP = LoadWidgetBlueprint(AssetPath);
	UAssetEditorSubsystem* AssetEditors = GEditor ? GEditor->GetEditorSubsystem<UAssetEditorSubsystem>() : nullptr;
	return BP && AssetEditors && AssetEditors->OpenEditorForAsset(BP);
}

#undef LOCTEXT_NAMESPACE
