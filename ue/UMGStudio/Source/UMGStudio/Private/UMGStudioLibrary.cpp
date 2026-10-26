#include "UMGStudioLibrary.h"
#include "UMGStudioOps.h"

bool UUMGStudioLibrary::ImportWidgetText(const FString& AssetPath, const FString& Text, const FString& ParentClass,
	const FString& DesignSizeMode, FVector2D DesignSize, FString& OutReport)
{
	FUMGStudioImportOptions Options;
	Options.AssetPath = AssetPath;
	Options.Text = Text;
	Options.ParentClass = ParentClass;
	Options.DesignSizeMode = DesignSizeMode;
	Options.DesignSize = DesignSize;
	const FUMGStudioImportResult Result = UMGStudio::ImportWidgetText(Options);
	TArray<FString> Lines;
	if (!Result.Error.IsEmpty())
	{
		Lines.Add(Result.Error);
	}
	Lines.Add(FString::Printf(TEXT("%s: виджетов %d, корень %s%s"), *AssetPath, Result.Widgets, *Result.Root,
		Result.bCreated ? TEXT(", создан") : TEXT("")));
	if (!Result.Backup.IsEmpty())
	{
		Lines.Add(TEXT("Копия: ") + Result.Backup);
	}
	Lines.Append(Result.Messages);
	OutReport = FString::Join(Lines, TEXT("\n"));
	return Result.bOk;
}

bool UUMGStudioLibrary::ExportWidgetText(const FString& AssetPath, FString& OutText)
{
	FString Error;
	const bool bOk = UMGStudio::ExportWidgetText(AssetPath, OutText, Error);
	if (!bOk)
	{
		OutText = Error;
	}
	return bOk;
}
