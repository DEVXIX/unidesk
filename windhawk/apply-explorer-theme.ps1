# Applies unidesk's "widgets" look to the Windows 11 File Explorer Styler mod.
# Run in an ELEVATED PowerShell (Win+X -> Terminal (Admin)):
#   powershell -ExecutionPolicy Bypass -File .\apply-explorer-theme.ps1
#
# Colours are unidesk's current wallpaper palette. If you change your wallpaper,
# ask unidesk to regenerate this file (the palette shifts with the wallpaper).

$ErrorActionPreference = 'Stop'
$base = 'HKLM:\SOFTWARE\Windhawk\Engine\Mods\windows-11-file-explorer-styler'
$s = "$base\Settings"

if (-not (Test-Path $s)) { throw "File Explorer Styler is not installed in Windhawk." }

# palette (unidesk, wallpaper source)
$surface   = '#0c0e12'   # window / content background
$card      = '#1c2026'   # surfaceContainerHigh  (tooltips)
$pill      = '#22262d'   # surfaceContainerHighest (address + search)
$accent    = '#3e5373'   # primaryContainer (selected tab)
$border    = '#444850'   # outlineVariant
$hover     = '#22262d'   # tab hover

# each entry: target + one-or-more styles
$entries = @(
  @{ t = 'TabViewItem > Grid#LayoutRoot > Canvas';            s = @('Visibility=Collapsed') }
  @{ t = 'TabViewItem > Grid#LayoutRoot';                     s = @('CornerRadius=6') }
  @{ t = 'TabViewItem > Grid#LayoutRoot@CommonStates';        s = @(
        "Background@Selected:=<SolidColorBrush Color=`"$accent`"/>",
        "Background@PointerOverSelected:=<SolidColorBrush Color=`"$accent`"/>",
        "Background@PressedSelected:=<SolidColorBrush Color=`"$accent`"/>",
        "Background@PointerOver:=<SolidColorBrush Color=`"$hover`"/>") }
  @{ t = 'CommandBar#FileExplorerCommandBar';                 s = @('Background=Transparent') }
  @{ t = 'FileExplorerExtensions.CommandBarControl_Wave1 > Grid, Grid#CommandBarControlRootGrid'; s = @('Background=Transparent','BorderThickness=0') }
  @{ t = 'Grid#NavigationBarControlGrid';                     s = @('Background=Transparent') }
  @{ t = 'FileExplorerExtensions.AddressBarControl > Grid#PART_LayoutRoot'; s = @("Background:=<SolidColorBrush Color=`"$accent`" Opacity=`"0.35`"/>",'CornerRadius=18','BorderThickness=0') }
  @{ t = 'AutoSuggestBox#FileExplorerSearchBox > Grid#LayoutRoot > TextBox > Grid@CommonStates > Border#BorderElement'; s = @("Background:=<SolidColorBrush Color=`"$accent`" Opacity=`"0.35`"/>",'CornerRadius=18','BorderThickness=0') }
  @{ t = 'Grid#HomeViewRootGrid';                            s = @("Background=$surface") }
  @{ t = 'Grid#DetailsViewControlRootGrid';                  s = @("Background=$surface") }
  @{ t = 'Microsoft.UI.Xaml.Controls.Grid#GalleryRootGrid'; s = @("Background=$surface") }
  @{ t = 'ToolTip';                                          s = @("Background:=<SolidColorBrush Color=`"$card`"/>",'CornerRadius=8') }
  @{ t = 'Microsoft.UI.Xaml.Controls.Primitives.NavigationViewItemPresenter#NavigationViewItemPresenter > Microsoft.UI.Xaml.Controls.Grid#LayoutRoot'; s = @('CornerRadius=6') }
  @{ t = 'Microsoft.UI.Xaml.Controls.Primitives.NavigationViewItemPresenter#NavigationViewItemPresenter > Microsoft.UI.Xaml.Controls.Grid#LayoutRoot@CommonStates'; s = @(
        "Background@Selected:=<SolidColorBrush Color=`"$accent`" Opacity=`"0.55`"/>",
        "Background@PointerOver:=<SolidColorBrush Color=`"$accent`" Opacity=`"0.22`"/>",
        "Background@PointerOverSelected:=<SolidColorBrush Color=`"$accent`" Opacity=`"0.6`"/>") }
)

# clear any stray style constant (must be a named constant, not a bare style)
Set-ItemProperty $s 'styleConstants[0]' '' -Type String

for ($i = 0; $i -lt $entries.Count; $i++) {
  Set-ItemProperty $s ("controlStyles[$i].target") $entries[$i].t -Type String
  $styles = $entries[$i].s
  for ($j = 0; $j -lt $styles.Count; $j++) {
    Set-ItemProperty $s ("controlStyles[$i].styles[$j]") $styles[$j] -Type String
  }
}

# tell the Windhawk engine to reload the mod
Set-ItemProperty $base 'SettingsChangeTime' ([int][double]::Parse((Get-Date -UFormat %s))) -Type DWord
Write-Host ("Applied {0} control styles. If Explorer doesn't refresh, toggle the mod off/on in Windhawk." -f $entries.Count)
