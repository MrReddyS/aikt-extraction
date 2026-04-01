#Requires -Version 5.1
<#
.SYNOPSIS
  Build in Azure Container Registry (az acr build).

.EXAMPLE
  .\deploy.ps1 -Reg creg_name -Sub "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" -Rg rg-mygroup
#>

param(
    [Parameter(Mandatory)]
    [string] $Reg,

    [Parameter(Mandatory)]
    [string] $Sub,

    [Parameter(Mandatory)]
    [string] $Rg,

    [string] $Image = "extraction",
    [string] $Context = "."
)

$ErrorActionPreference = "Stop"
$LoginServer = "$Reg.azurecr.io"
$FullImage = "$LoginServer/${Image}:latest"

Write-Host "Subscription: $Sub"
Write-Host "Registry:     $LoginServer (RG: $Rg)"
Write-Host "Image:        $FullImage"
Write-Host ""

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Error "Azure CLI not found. Install: https://learn.microsoft.com/cli/azure/install-azure-cli"
}

az account set --subscription $Sub | Out-Null

az acr build `
  --registry $Reg `
  --image "${Image}:latest" `
  --file Dockerfile `
  $Context

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Built and pushed: $FullImage"
