{{/*
Expand the name of the chart.
*/}}
{{- define "tobogganing-spire.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "tobogganing-spire.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "tobogganing-spire.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "tobogganing-spire.labels" -}}
helm.sh/chart: {{ include "tobogganing-spire.chart" . }}
{{ include "tobogganing-spire.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "tobogganing-spire.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tobogganing-spire.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Server selector labels
*/}}
{{- define "tobogganing-spire.serverSelectorLabels" -}}
{{ include "tobogganing-spire.selectorLabels" . }}
component: server
{{- end }}

{{/*
Agent selector labels
*/}}
{{- define "tobogganing-spire.agentSelectorLabels" -}}
{{ include "tobogganing-spire.selectorLabels" . }}
component: agent
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "tobogganing-spire.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "tobogganing-spire.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Namespace
*/}}
{{- define "tobogganing-spire.namespace" -}}
{{- default "spire-system" .Values.spire.namespace }}
{{- end }}
