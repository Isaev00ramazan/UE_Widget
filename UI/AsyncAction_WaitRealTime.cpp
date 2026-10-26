#include "UI/AsyncAction_WaitRealTime.h"

namespace
{
	/** Ждущие Retriggerable: (виджет, ключ) → последнее действие */
	TMap<TPair<TWeakObjectPtr<UObject>, FName>, TWeakObjectPtr<UAsyncAction_WaitRealTime>> GPendingRetrigger;
}

UAsyncAction_WaitRealTime* UAsyncAction_WaitRealTime::WaitRealTime(UObject* WorldContextObject, float Seconds)
{
	UAsyncAction_WaitRealTime* Action = NewObject<UAsyncAction_WaitRealTime>();
	Action->Seconds = FMath::Max(0.0f, Seconds);
	// Держит действие живым до SetReadyToDestroy — иначе GC собрал бы его посреди ожидания
	Action->RegisterWithGameInstance(WorldContextObject);
	return Action;
}

UAsyncAction_WaitRealTime* UAsyncAction_WaitRealTime::WaitRealTimeRetriggerable(UObject* WorldContextObject, float Seconds, FName Key)
{
	UAsyncAction_WaitRealTime* Action = WaitRealTime(WorldContextObject, Seconds);
	Action->bRetriggerable = true;
	Action->RetriggerOwner = WorldContextObject;
	Action->RetriggerKey   = Key;
	return Action;
}

void UAsyncAction_WaitRealTime::Cancel()
{
	if (TickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(TickerHandle);
		TickerHandle.Reset();
	}
	SetReadyToDestroy();
}

void UAsyncAction_WaitRealTime::Activate()
{
	if (bRetriggerable && RetriggerOwner.IsValid())
	{
		// Записи закрытых виджетов и отработавших действий — чистим, чтобы карта не росла
		for (auto It = GPendingRetrigger.CreateIterator(); It; ++It)
		{
			if (!It.Key().Key.IsValid() || !It.Value().IsValid())
			{
				It.RemoveCurrent();
			}
		}

		// Прошлый вызов с тем же ключом больше не нужен — срабатывает только последний
		const TPair<TWeakObjectPtr<UObject>, FName> PendingKey(RetriggerOwner, RetriggerKey);
		if (TWeakObjectPtr<UAsyncAction_WaitRealTime>* Previous = GPendingRetrigger.Find(PendingKey))
		{
			if (UAsyncAction_WaitRealTime* Old = Previous->Get(); Old && Old != this)
			{
				Old->Cancel();
			}
		}
		GPendingRetrigger.Add(PendingKey, this);
	}

	// Core-тикер идёт от реального времени и не знает о паузе мира — в отличие от Delay и таймеров мира
	TickerHandle = FTSTicker::GetCoreTicker().AddTicker(
		FTickerDelegate::CreateUObject(this, &UAsyncAction_WaitRealTime::HandleTick), Seconds);
}

bool UAsyncAction_WaitRealTime::HandleTick(float DeltaTime)
{
	TickerHandle.Reset();
	if (bRetriggerable)
	{
		// Виджет уже закрыт и удалён — продолжать его ветку некуда
		if (!RetriggerOwner.IsValid())
		{
			SetReadyToDestroy();
			return false;
		}
		GPendingRetrigger.Remove(TPair<TWeakObjectPtr<UObject>, FName>(RetriggerOwner, RetriggerKey));
	}
	Completed.Broadcast();
	SetReadyToDestroy();
	return false; // один раз
}
