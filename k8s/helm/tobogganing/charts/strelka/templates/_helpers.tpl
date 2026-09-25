{{/*
Strelka sub-chart naming/label helpers. Self-contained — subcharts render
independently of the parent chart's templates/_helpers.tpl.
*/}}
{{- define "strelka.fullname" -}}
{{- printf "%s-strelka" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "strelka.labels" -}}
app.kubernetes.io/name: strelka
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: tobogganing
app.kubernetes.io/component: sase-adapter-tool
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end }}

{{- define "strelka.selectorLabels" -}}
app.kubernetes.io/name: strelka
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
