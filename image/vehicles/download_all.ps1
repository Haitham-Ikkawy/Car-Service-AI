# Vehicle Image Downloader - CarDekho Source
# Downloads exterior front-left images for all vehicle models

$ErrorActionPreference = "Continue"
$baseDir = "C:\workbench\fastAPI\Car_Service_AI\image\vehicles"
$logFile = "C:\workbench\fastAPI\Car_Service_AI\image\vehicles\download_log.txt"
$results = @()

function To-Slug {
    param([string]$text)
    return $text.ToLower() -replace '[^a-z0-9]+', '-' -replace '-+', '-' -replace '^-|-$', ''
}

# Complete brand/model to CarDekho slug mapping
$mapping = @{
    "Acura" = @("ilx", "tlx", "rdx", "mdx")
    "Alfa Romeo" = @("giulia", "stelvio", "tonale")
    "Aston Martin" = @("vantage", "db12", "dbx")
    "Audi" = @("a3", "a4", "a6", "q3", "q5", "q7", "e-tron")
    "Bentley" = @("continental-gt", "flying-spur", "bentayga")
    "BMW" = @("1-series", "3-series", "5-series", "x1", "x3", "x5", "i4")
    "Buick" = @("encore", "envision", "lacrosse")
    "Cadillac" = @("ct4", "ct5", "xt4", "xt5", "escalade")
    "Chevrolet" = @("spark", "cruze", "malibu", "trailblazer", "equinox")
    "Chrysler" = @("300", "pacifica")
    "Citroen" = @("c1", "c3", "c4", "c5", "berlingo")
    "Dodge" = @("challenger", "charger", "durango")
    "Ferrari" = @("roma", "sf90-stradale", "296-gtb", "812-superfast", "f8-tributo")
    "Fiat" = @("500", "panda", "punto", "tipo")
    "Ford" = @("fiesta", "focus", "mustang", "ranger", "escape", "explorer")
    "Genesis" = @("g70", "g80", "g90", "gv70", "gv80")
    "GMC" = @("terrain", "acadia", "yukon", "sierra")
    "Honda" = @("civic", "accord", "cr-v", "hr-v", "city", "fit")
    "Hyundai" = @("i20", "i30", "tucson", "santa-fe", "elantra", "kona")
    "Infiniti" = @("q50", "q60", "qx50", "qx60")
    "Jaguar" = @("xe", "xf", "f-pace", "e-pace", "i-pace")
    "Jeep" = @("renegade", "compass", "cherokee", "wrangler", "grand-cherokee")
    "Kia" = @("rio", "ceed", "sportage", "sorento", "picanto", "ev6")
    "Lamborghini" = @("huracan", "urus", "revuelto")
    "Land Rover" = @("range-rover", "discovery", "defender", "evoque")
    "Lexus" = @("ux", "nx", "rx", "es", "ls")
    "Lincoln" = @("corsair", "aviator", "navigator")
    "Maserati" = @("ghibli", "levante", "grecale", "granturismo")
    "Mazda" = @("2", "3", "6", "cx-3", "cx-5", "mx-5")
    "McLaren" = @("720s", "750s", "artura", "gt")
    "Mercedes-Benz" = @("a-class", "c-class", "e-class", "glc", "gle", "eqc")
    "Mitsubishi" = @("lancer", "outlander", "asx", "pajero")
    "Nissan" = @("micra", "qashqai", "x-trail", "leaf", "altima")
    "Opel" = @("corsa", "astra", "insignia", "mokka", "grandland")
    "Peugeot" = @("208", "308", "3008", "5008", "2008")
    "Porsche" = @("911", "cayenne", "macan", "taycan", "panamera")
    "Ram" = @("1500", "2500", "3500")
    "Renault" = @("clio", "megane", "captur", "duster", "arkana")
    "Rolls-Royce" = @("ghost", "phantom", "cullinan", "spectre")
    "Seat" = @("ibiza", "leon", "arona", "ateca", "tarraco")
    "Skoda" = @("fabia", "octavia", "superb", "karoq", "kodiaq")
    "Smart" = @("fortwo", "forfour")
    "Subaru" = @("impreza", "forester", "outback", "xv", "wrx")
    "Suzuki" = @("swift", "baleno", "vitara", "jimny", "ertiga")
    "Tesla" = @("model-3", "model-y", "model-s", "model-x")
    "Toyota" = @("corolla", "camry", "rav4", "land-cruiser", "yaris", "prius", "hilux")
    "Volkswagen" = @("golf", "passat", "tiguan", "polo", "touareg", "arteon")
    "Volvo" = @("s60", "s90", "xc40", "xc60", "xc90")
}

function Download-ModelImage {
    param(
        [string]$brand,
        [string]$modelSlug,
        [string]$brandSlug
    )
    
    $picturesUrl = "https://www.cardekho.com/$brandSlug/$modelSlug/pictures"
    
    try {
        $page = Invoke-WebRequest -Uri $picturesUrl -UseBasicParsing -TimeoutSec 10 -Headers @{
            "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # Extract exterior image URLs - prefer front-left-side
        $content = $page.Content
        $pattern = 'https?://stimg\.cardekho\.com/images/carexteriorimages/[^"''>\s]+'
        $allImages = [regex]::Matches($content, $pattern) | ForEach-Object { $_.Value } | Sort-Object -Unique
        
        # Prefer front-left-side, then front-right-view, then any exterior
        $frontLeft = $allImages | Where-Object { $_ -match 'front-left-side' } | Select-Object -First 1
        $frontRight = $allImages | Where-Object { $_ -match 'front-right-view' } | Select-Object -First 1
        $anyExterior = $allImages | Where-Object { $_ -match 'exterior-image|front-left|front-right|side-view' } | Select-Object -First 1
        
        $imageUrl = $frontLeft
        if (-not $imageUrl) { $imageUrl = $frontRight }
        if (-not $imageUrl) { $imageUrl = $anyExterior }
        if (-not $imageUrl -and $allImages.Count -gt 0) { $imageUrl = $allImages[0] }
        
        if ($imageUrl) {
            # Use 630x420 size for smaller file size
            $downloadUrl = $imageUrl -replace '930x620', '630x420'
            
            $brandDir = Join-Path $baseDir $brandSlug
            if (-not (Test-Path $brandDir)) { New-Item -ItemType Directory -Path $brandDir -Force | Out-Null }
            
            $ext = if ($downloadUrl -match '\.webp$') { "webp" } else { "jpg" }
            $outFile = Join-Path $brandDir "$modelSlug.$ext"
            
            Invoke-WebRequest -Uri $downloadUrl -OutFile $outFile -UseBasicParsing -TimeoutSec 15 -Headers @{
                "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            $size = (Get-Item $outFile).Length
            return @{ ok=$true; url=$downloadUrl; file=$outFile; size=$size; ext=$ext }
        } else {
            return @{ ok=$false; error="No exterior image found on page" }
        }
    } catch {
        return @{ ok=$false; error=$_.Exception.Message }
    }
}

# Process all brands
$totalModels = 0
$successCount = 0
$failCount = 0
$failedModels = @()

foreach ($brand in $mapping.Keys) {
    $brandSlug = To-Slug $brand
    $models = $mapping[$brand]
    
    Write-Host "`n=== Processing $brand ($($models.Count) models) ===" -ForegroundColor Cyan
    
    foreach ($model in $models) {
        $totalModels++
        $modelName = $model -replace '-', ' '
        # Capitalize first letter of each word
        $modelName = ($model -split '-' | ForEach-Object { $_.Substring(0,1).ToUpper() + $_.Substring(1) }) -join ' '
        
        Write-Host "  $brand $modelName... " -NoNewline
        
        $result = Download-ModelImage -brand $brand -modelSlug $model -brandSlug $brandSlug
        
        if ($result.ok) {
            $successCount++
            Write-Host "OK ($([math]::Round($result.size/1024))KB)" -ForegroundColor Green
            $results += [PSCustomObject]@{ Brand=$brand; Model=$modelName; Status="OK"; File=$result.file; Size=$result.size }
        } else {
            $failCount++
            Write-Host "FAIL: $($result.error)" -ForegroundColor Yellow
            $failedModels += [PSCustomObject]@{ Brand=$brand; Model=$modelName; Slug=$model; Error=$result.error }
            $results += [PSCustomObject]@{ Brand=$brand; Model=$modelName; Status="MISSING"; File=""; Size=0 }
        }
        
        # Rate limiting - 0.5s between requests
        Start-Sleep -Milliseconds 500
    }
}

# Summary
Write-Host "`n========================================" -ForegroundColor White
Write-Host "DOWNLOAD COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor White
Write-Host "Total models: $totalModels"
Write-Host "Successfully downloaded: $successCount" -ForegroundColor Green
Write-Host "Failed/missing: $failCount" -ForegroundColor Yellow

# Save log
$results | Out-File $logFile -Encoding UTF8
Write-Host "`nLog saved to: $logFile"

if ($failedModels.Count -gt 0) {
    Write-Host "`nFailed models:" -ForegroundColor Yellow
    $failedModels | ForEach-Object { Write-Host "  - $($_.Brand) $($_.Model) ($($_.Slug)): $($_.Error)" }
}
