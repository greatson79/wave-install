$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../lib/install-help.ps1')
$cases=@(
  @('mail tester+tag@example.co.kr','mail <EMAIL>'),
  @('Authorization: bEaReR aBc_123+/=-','Authorization: <TOKEN>'),
  @('key sk-abcdefgh1234','key <TOKEN>'),
  @('abcdefghijklmnopqrst#abcdefgh','<LOGIN_CODE>'),
  @('Paste code here if prompted > secret-code','Paste code here if prompted > <LOGIN_CODE>'),
  @('C:\Users\Someone\project','C:\Users\<USER>\project'),
  @('C:/Users/Someone/project','C:\Users\<USER>/project'),
  @('/Users/Someone/project /home/Someone/project','/Users/<USER>/project /Users/<USER>/project'),
  @("USERNAME=someone`nwhoami: DOMAIN\someone","USERNAME=<USER>`nwhoami: <USER>"),
  @('ghp_abcdefghijklmnopqrst github_pat_abcdefghijklmnopqrst','<TOKEN> <TOKEN>'),
  @('Hi Person.Name and PERSON.NAME','Hi <USER> and <USER>')
)
foreach($case in $cases){
  $actual=ConvertTo-HelpSafeText $case[0] 'Person.Name'
  if($actual -cne $case[1]){throw "redaction mismatch: expected=$($case[1]) actual=$actual"}
}
$unsafe="line1`nline2`t"+[char]27+'[31m'+[char]0+[char]13+'tail'
$plain=ConvertTo-HelpSafeText $unsafe ''
if($plain -match '[\x00-\x08\x0b-\x1f\x7f]'){throw 'control character remains'}
if(-not $plain.Contains("line1`nline2`t")){throw 'newlines/tabs lost'}
if((ConvertTo-HelpSafeText 'Person.NameSuffix' 'Person.Name') -cne 'Person.NameSuffix'){throw 'username boundary lost'}
if((ConvertTo-HelpSafeText '' '') -cne ''){throw 'empty text changed'}
if((ConvertTo-HelpSafeText '<USER> <EMAIL> <TOKEN> <LOGIN_CODE>' '') -cne '<USER> <EMAIL> <TOKEN> <LOGIN_CODE>'){throw 'markers changed'}
Write-Host 'PASS pure Windows help redaction: eight rules, homes, username, controls'

$spaced=ConvertTo-HelpSafeText 'C:\Users\Alice Smith\project /Users/Alice Smith/project /home/Alice Smith/project' 'Alice Smith'
if($spaced -match 'Alice|Smith'){throw 'spaced account leaked'}
$ansiToken='sk-abcd'+[char]27+'[31m'+'efghijkl'
if((ConvertTo-HelpSafeText $ansiToken '') -cne '<TOKEN>'){throw 'ANSI CSI token bypass'}
$oscToken='sk-abcd'+[char]27+']0;window title'+[char]7+'efghijkl'
if((ConvertTo-HelpSafeText $oscToken '') -cne '<TOKEN>'){throw 'ANSI OSC token bypass'}
$oscTerminator='sk-abcd'+[char]27+']0;window title'+[char]27+'\'+'efghijkl'
if((ConvertTo-HelpSafeText $oscTerminator '') -cne '<TOKEN>'){throw 'ANSI OSC ST token bypass'}
Write-Host 'PASS spaced usernames and ANSI CSI/OSC token bypass guards'
