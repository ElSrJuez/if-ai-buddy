$baseurl = "http://phantompi4:8889"
Invoke-WebRequest -Uri "$baseurl"

$titlesResponse = Invoke-WebRequest -Uri "$baseurl/titles"
$games = ($titlesResponse.Content | ConvertFrom-Json)

if (-not $games) {
	Write-Host "No games available yet. Drop a .z3-.z8 file into /root/zcode and restart the server."
	return
}

$ongoingGames = Invoke-WebRequest -Uri "$baseurl/games"
$ongoingGames | Out-Host

$gameFile = ($games| Where-Object zfile -Like "*z3").zFile
$featuredGame = $gameFile -replace '\.z[3-8]$', ''

$payload = @{ game = $featuredGame; label = "loop-test" } | ConvertTo-Json
$sessionResponse = Invoke-WebRequest -Method Post -Uri "$baseurl/games" -Body $payload -ContentType 'application/json' -UseBasicParsing -ErrorAction SilentlyContinue
if (-not $sessionResponse) {
	Write-Host "Failed to reach $baseurl/games: $($Error[0].Exception.Message)"
	return
}
$sessionResponse | Out-Host

if ($sessionResponse.StatusCode -ge 300) {
	Write-Host "Game start failed with $($sessionResponse.StatusCode) $($sessionResponse.StatusDescription):`n$($sessionResponse.Content)"
	return
}

remove-variable session, sessionpid -ErrorAction silentlycontinue
$session = $sessionResponse.Content | ConvertFrom-Json
$sessionPid = $session.pid
if (-not $sessionPid) {
	Write-Host "Game start response did not include a PID. Raw body:`n$($sessionResponse.Content)"
	return
}
Write-Host "Started $gameFile with PID $sessionPid"

$actions = @(
	'look',
	'open door',
	'go north',
	'inventory'
)

foreach ($action in $actions) {
	$myUri = "$baseurl/games/$sessionPid/action"
	$myBody = @{ action = $action }
	Write-host "submitting action with uri $myUri" 
	$myBody | out-host
	$resp = Invoke-RestMethod -Method Post -Uri  $myUri -Body ($myBody | ConvertTo-Json) -ContentType 'application/json'
	$resp | fl * | out-host
	Start-Sleep -Seconds 1
}

Invoke-WebRequest -Method Delete -Uri "$baseurl/games/$sessionPid" | Out-Null
Write-Host "Cleaned up PID $sessionPid"


# commands to send
$actions = @(
    'look',
    'open door',
    'go north',
    'inventory'
)

foreach ($action in $actions) {
    $uri  = "$baseurl/games/$sessionPid/action"
    $body = @{ action = $action } | ConvertTo-Json

    Write-Host "→ $action"
    $resp = Invoke-RestMethod -Method Post -Uri $uri -Body $body -ContentType 'application/json'

    # standard fields
    $resp.pid   | Out-Null   # ensure pid exists
    Write-Host "Location :"  $resp.location
    Write-Host "Score    :"  $resp.score
    Write-Host "Moves    :"  $resp.moves
    Write-Host "Text ----`n$($resp.data)`n"

    # debug extras (present only in DEBUG build)
    if ($resp.PSObject.Properties.Name -contains 'vm') {
        Write-Host "VM PC     :" ("0x{0:X}" -f $resp.vm.pc)
        Write-Host "Stack     :" ($resp.vm.stack -join ', ')
        Write-Host "Locals    :" ($resp.vm.locals -join ', ')
        if ($resp.vm.globals) {
            Write-Host "Globals   :" ($resp.vm.globals.GetEnumerator() | Sort-Object Name |
                                         ForEach-Object { "$($_.Name)=$($_.Value)" } -join ' ')
        }
    }
    if ($resp.PSObject.Properties.Name -contains 'objectOp') {
        $o = $resp.objectOp
        Write-Host "ObjEvent :" "$($o.action) obj=$($o.obj) parent=$($o.parent)"
    }

    Write-Host '--------------------------'
    Start-Sleep -Milliseconds 500
}