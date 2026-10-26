// UMG Studio Bridge: локальный HTTP в редакторе, через него программа UMG Studio заливает и забирает виджеты.
//
//   GET  /umgstudio/ping                     → {"ok", "engine", "project"}
//   POST /umgstudio/import  {asset, text, parent?, designSizeMode?, designSize?, backup?, open?}
//   POST /umgstudio/export  {asset}          → {"ok", "text"}
//   POST /umgstudio/open    {asset}
//
// Порт: [UMGStudio] Port=30110 в Config/DefaultEditorPerProjectUserSettings.ini (по умолчанию 30110).
// Запросы обрабатываются на игровом потоке (HTTPServer тикает там же) — API редактора можно звать напрямую.

#include "Dom/JsonObject.h"
#include "HttpPath.h"
#include "HttpRouteHandle.h"
#include "HttpServerModule.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "IHttpRouter.h"
#include "Misc/App.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/EngineVersion.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UMGStudioOps.h"

DEFINE_LOG_CATEGORY_STATIC(LogUMGStudio, Log, All);

namespace
{
	FString BodyOf(const FHttpServerRequest& Request)
	{
		const FUTF8ToTCHAR Conv(reinterpret_cast<const ANSICHAR*>(Request.Body.GetData()), Request.Body.Num());
		return FString(Conv.Length(), Conv.Get());
	}

	TSharedPtr<FJsonObject> ParseJson(const FString& Text)
	{
		TSharedPtr<FJsonObject> Object;
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
		FJsonSerializer::Deserialize(Reader, Object);
		return Object;
	}

	void Reply(const FHttpResultCallback& OnComplete, const TSharedRef<FJsonObject>& Object)
	{
		FString Out;
		const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
		FJsonSerializer::Serialize(Object, Writer);
		OnComplete(FHttpServerResponse::Create(Out, TEXT("application/json; charset=utf-8")));
	}

	void ReplyError(const FHttpResultCallback& OnComplete, const FString& Error)
	{
		const TSharedRef<FJsonObject> Object = MakeShared<FJsonObject>();
		Object->SetBoolField(TEXT("ok"), false);
		Object->SetStringField(TEXT("error"), Error);
		Reply(OnComplete, Object);
	}

	TArray<TSharedPtr<FJsonValue>> ToJsonArray(const TArray<FString>& Items)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const FString& Item : Items)
		{
			Out.Add(MakeShared<FJsonValueString>(Item));
		}
		return Out;
	}
}

class FUMGStudioModule : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
		int32 Port = 30110;
		GConfig->GetInt(TEXT("UMGStudio"), TEXT("Port"), Port, GEditorPerProjectIni);

		FHttpServerModule& Http = FHttpServerModule::Get();
		Router = Http.GetHttpRouter(Port, /*bFailOnBindFailure*/ true);
		if (!Router.IsValid())
		{
			UE_LOG(LogUMGStudio, Error, TEXT("[UMGStudio] порт %d занят — мост не запущен (смени [UMGStudio] Port)"), Port);
			return;
		}
		Bind(TEXT("/umgstudio/ping"), EHttpServerRequestVerbs::VERB_GET, &FUMGStudioModule::HandlePing);
		Bind(TEXT("/umgstudio/import"), EHttpServerRequestVerbs::VERB_POST, &FUMGStudioModule::HandleImport);
		Bind(TEXT("/umgstudio/export"), EHttpServerRequestVerbs::VERB_POST, &FUMGStudioModule::HandleExport);
		Bind(TEXT("/umgstudio/open"), EHttpServerRequestVerbs::VERB_POST, &FUMGStudioModule::HandleOpen);
		Http.StartAllListeners();
		UE_LOG(LogUMGStudio, Display, TEXT("[UMGStudio] мост слушает http://127.0.0.1:%d/umgstudio"), Port);
	}

	virtual void ShutdownModule() override
	{
		if (Router.IsValid())
		{
			for (const FHttpRouteHandle& Handle : Handles)
			{
				Router->UnbindRoute(Handle);
			}
		}
		Handles.Reset();
		Router.Reset();
	}

private:
	using FHandler = bool (FUMGStudioModule::*)(const FHttpServerRequest&, const FHttpResultCallback&);

	void Bind(const TCHAR* Path, EHttpServerRequestVerbs Verb, FHandler Handler)
	{
		Handles.Add(Router->BindRoute(FHttpPath(Path), Verb,
			FHttpRequestHandler::CreateLambda([this, Handler](const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
			{
				return (this->*Handler)(Request, OnComplete);
			})));
	}

	bool HandlePing(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
	{
		const TSharedRef<FJsonObject> Object = MakeShared<FJsonObject>();
		Object->SetBoolField(TEXT("ok"), true);
		Object->SetStringField(TEXT("engine"), FEngineVersion::Current().ToString());
		Object->SetStringField(TEXT("project"), FApp::GetProjectName());
		Reply(OnComplete, Object);
		return true;
	}

	bool HandleImport(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
	{
		const TSharedPtr<FJsonObject> In = ParseJson(BodyOf(Request));
		if (!In.IsValid())
		{
			ReplyError(OnComplete, TEXT("Тело запроса — не JSON"));
			return true;
		}
		FUMGStudioImportOptions Options;
		Options.AssetPath = In->GetStringField(TEXT("asset"));
		Options.Text = In->GetStringField(TEXT("text"));
		In->TryGetStringField(TEXT("parent"), Options.ParentClass);
		In->TryGetStringField(TEXT("designSizeMode"), Options.DesignSizeMode);
		const TArray<TSharedPtr<FJsonValue>>* Size = nullptr;
		if (In->TryGetArrayField(TEXT("designSize"), Size) && Size->Num() == 2)
		{
			Options.DesignSize = FVector2D((*Size)[0]->AsNumber(), (*Size)[1]->AsNumber());
		}
		In->TryGetBoolField(TEXT("backup"), Options.bBackup);
		In->TryGetBoolField(TEXT("open"), Options.bOpenEditor);

		const FUMGStudioImportResult Result = UMGStudio::ImportWidgetText(Options);
		UE_LOG(LogUMGStudio, Display, TEXT("[UMGStudio] %s: %s"), *Options.AssetPath,
			Result.bOk ? TEXT("записан") : *Result.Error);

		const TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetBoolField(TEXT("ok"), Result.bOk);
		Out->SetStringField(TEXT("error"), Result.Error);
		Out->SetStringField(TEXT("asset"), Options.AssetPath);
		Out->SetBoolField(TEXT("created"), Result.bCreated);
		Out->SetStringField(TEXT("backup"), Result.Backup);
		Out->SetStringField(TEXT("root"), Result.Root);
		Out->SetNumberField(TEXT("widgets"), Result.Widgets);
		Out->SetNumberField(TEXT("compileErrors"), Result.CompileErrors);
		Out->SetNumberField(TEXT("compileWarnings"), Result.CompileWarnings);
		Out->SetArrayField(TEXT("messages"), ToJsonArray(Result.Messages));
		Out->SetArrayField(TEXT("renamed"), ToJsonArray(Result.Renamed));
		Reply(OnComplete, Out);
		return true;
	}

	bool HandleExport(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
	{
		const TSharedPtr<FJsonObject> In = ParseJson(BodyOf(Request));
		FString Asset, Text, Error;
		if (!In.IsValid() || !In->TryGetStringField(TEXT("asset"), Asset))
		{
			ReplyError(OnComplete, TEXT("Нужно поле asset"));
			return true;
		}
		if (!UMGStudio::ExportWidgetText(Asset, Text, Error))
		{
			ReplyError(OnComplete, Error);
			return true;
		}
		const TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetBoolField(TEXT("ok"), true);
		Out->SetStringField(TEXT("asset"), Asset);
		Out->SetStringField(TEXT("text"), Text);
		Reply(OnComplete, Out);
		return true;
	}

	bool HandleOpen(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
	{
		const TSharedPtr<FJsonObject> In = ParseJson(BodyOf(Request));
		FString Asset;
		const bool bOk = In.IsValid() && In->TryGetStringField(TEXT("asset"), Asset) && UMGStudio::OpenWidgetEditor(Asset);
		const TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetBoolField(TEXT("ok"), bOk);
		Reply(OnComplete, Out);
		return true;
	}

	TSharedPtr<IHttpRouter> Router;
	TArray<FHttpRouteHandle> Handles;
};

IMPLEMENT_MODULE(FUMGStudioModule, UMGStudio)
