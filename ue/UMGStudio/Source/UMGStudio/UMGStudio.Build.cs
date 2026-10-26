using UnrealBuildTool;

public class UMGStudio : ModuleRules
{
	public UMGStudio(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"UMG", "UMGEditor", "UnrealEd", "Kismet", "AssetTools", "Slate", "SlateCore",
			"HTTPServer", "Json", "JsonUtilities", "AssetRegistry"
		});
	}
}
