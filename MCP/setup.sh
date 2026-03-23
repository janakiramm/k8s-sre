helm upgrade -i kubernetes-mcp-server \
  -n mcp --create-namespace \
  oci://ghcr.io/containers/charts/kubernetes-mcp-server \
  -f mcp-values.yaml