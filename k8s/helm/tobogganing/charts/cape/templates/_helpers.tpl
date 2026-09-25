{{/*
CAPE sub-chart naming/label helpers. Self-contained — subcharts render
independently of the parent chart's templates/_helpers.tpl.
*/}}
{{- define "cape.fullname" -}}
{{- printf "%s-cape" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cape.labels" -}}
app.kubernetes.io/name: cape
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: tobogganing
app.kubernetes.io/component: sase-adapter-tool
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end }}

{{- define "cape.selectorLabels" -}}
app.kubernetes.io/name: cape
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
