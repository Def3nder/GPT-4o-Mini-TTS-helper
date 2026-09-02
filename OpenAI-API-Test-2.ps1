param(
    [Parameter(Mandatory = $true)]
    [Alias('input')]
    [string]$InputFile
)

if (-not (Test-Path -Path $InputFile -PathType Leaf)) {
    throw "Die Datei '$InputFile' wurde nicht gefunden."
}

$text = [string](Get-Content -Path $InputFile -Raw -Encoding UTF8)
if ([string]::IsNullOrWhiteSpace($text)) {
    throw "Die Eingabedatei ist leer."
}

Write-Host "Typ von `$text: $($text.GetType().FullName)"
Write-Host "Länge von `$text: $($text.Length) Zeichen"

$approxTokens = [math]::Ceiling($text.Length / 4)
if ($approxTokens -gt 2000) {
    Write-Warning "Text hat geschätzt ca. $approxTokens Tokens - das Limit von gpt-4o-mini-tts liegt bei 2000. Ggf. Text kürzen oder aufteilen."
}

$apiKey = [Environment]::GetEnvironmentVariable(
    'GPT-4o-Mini-TTS-Key',
    'User'
)
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw 'Die Umgebungsvariable wurde nicht gefunden.'
}

$headers = @{
    Authorization = "Bearer $apiKey"
}

$instructions = @"
Voice Affect: warm, calm, grounded
Tone: empathetic, intelligent, trustworthy
Pacing: slow
Emotion: gentle
Pronunciation: clear German pronunciation
Pauses: allow meaningful pauses after important sentences
Style: Speak like an experienced psychologist talking to one person. Never sound like a news reader.
"@

$bodyObj = [ordered]@{
    model        = 'gpt-4o-mini-tts'
    voice        = 'cedar'
    input        = $text
    instructions = $instructions
}

$body = $bodyObj | ConvertTo-Json -Depth 5

# DEBUG: zeig die ersten 400 Zeichen des generierten JSON,
# um zu sehen wie "input" tatsächlich serialisiert wurde
Write-Host "----- Body-Vorschau -----"
Write-Host $body.Substring(0, [Math]::Min(400, $body.Length))
Write-Host "-------------------------"

$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)

try {
    Invoke-WebRequest `
        -Uri 'https://api.openai.com/v1/audio/speech' `
        -Method Post `
        -Headers $headers `
        -ContentType 'application/json; charset=utf-8' `
        -Body $bodyBytes `
        -OutFile '.\speech-test.mp3'

    Write-Host "Fertig: speech-test.mp3 wurde erstellt."
}
catch {
    $errorMessage = $null

    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
        $errorMessage = $_.ErrorDetails.Message
    }
    elseif ($_.Exception.Response) {
        try {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $errorMessage = $reader.ReadToEnd()
        }
        catch {
            $errorMessage = "Antworttext konnte nicht gelesen werden: $($_.Exception.Message)"
        }
    }

    if ([string]::IsNullOrWhiteSpace($errorMessage)) {
        $errorMessage = $_.Exception.Message
    }

    Write-Error "API-Fehler: $errorMessage"
}

Remove-Variable apiKey
