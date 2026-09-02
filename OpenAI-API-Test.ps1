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

$body = @{
    model        = 'gpt-4o-mini-tts'
    voice        = 'cedar'
    input        = 'Dies ist ein kurzer Test der Text-zu-Sprache-Ausgabe.'
    instructions = 'Sprich natürlich, ruhig und klar auf Deutsch.'
} | ConvertTo-Json

Invoke-WebRequest `
    -Uri 'https://api.openai.com/v1/audio/speech' `
    -Method Post `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $body `
    -OutFile '.\speech-test.mp3'

Remove-Variable apiKey