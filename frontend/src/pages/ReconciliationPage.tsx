import { useEffect, useState } from "react";
import { Alert, Button, Card, DatePicker, Form, InputNumber, Select, Space, Statistic, Table, Tag, Upload, message } from "antd";
import { InboxOutlined, ThunderboltOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  DailyReconResult,
  GasSource,
  UploadResponse,
  listGasSources,
  reconcileDaily,
  uploadUpstreamDaily,
} from "../api/resources";

const VERDICT_COLOR: Record<string, string> = { PASS: "green", WARN: "orange", FAIL: "red" };

export default function ReconciliationPage() {
  const [sources, setSources] = useState<GasSource[]>([]);
  const [result, setResult] = useState<DailyReconResult | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [form] = Form.useForm();
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    listGasSources({ size: 200 }).then((r) => setSources(r.items));
  }, []);

  const onRun = async () => {
    const v = await form.validateFields();
    try {
      const r = await reconcileDaily({
        source_id: v.source_id,
        business_date: v.business_date.format("YYYY-MM-DD"),
        upstream_volume_nm3: v.upstream_volume_nm3,
      });
      setResult(r);
    } catch {
      /* toast handled */
    }
  };

  const onUpload = async (file: File) => {
    setUploading(true);
    try {
      const r = await uploadUpstreamDaily(file);
      setUploadResult(r);
      message.success(`成功 ${r.success} 行，失败 ${r.failed} 行`);
    } finally {
      setUploading(false);
    }
    return false; // 阻止 antd 自动上传
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card title="手动日对账" extra={<ThunderboltOutlined />}>
        <Form form={form} layout="inline" onFinish={onRun} initialValues={{ business_date: dayjs().subtract(1, "day") }}>
          <Form.Item name="source_id" label="气源" rules={[{ required: true }]}>
            <Select style={{ width: 240 }} options={sources.map((s) => ({ value: s.id, label: `${s.code} ${s.name}` }))} />
          </Form.Item>
          <Form.Item name="business_date" label="业务日期" rules={[{ required: true }]}>
            <DatePicker />
          </Form.Item>
          <Form.Item name="upstream_volume_nm3" label="上游计量(Nm³)" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: 180 }} />
          </Form.Item>
          <Button type="primary" htmlType="submit">执行对账</Button>
        </Form>

        {result && (
          <div style={{ marginTop: 16 }}>
            <Alert
              type={result.verdict === "PASS" ? "success" : result.verdict === "WARN" ? "warning" : "error"}
              showIcon
              message={
                <span>
                  对账判定 <Tag color={VERDICT_COLOR[result.verdict]}>{result.verdict}</Tag> — {result.reason}
                </span>
              }
            />
            <Space size="large" style={{ marginTop: 16 }}>
              <Statistic title="厂内 (Nm³)" value={result.plant_volume_nm3} precision={3} groupSeparator="," />
              <Statistic title="上游 (Nm³)" value={result.upstream_volume_nm3} precision={3} groupSeparator="," />
              <Statistic title="差值 (Nm³)" value={result.absolute_diff_nm3} precision={3} groupSeparator="," />
              <Statistic title="相对偏差 (%)" value={result.relative_diff_pct} precision={3} />
              <Statistic title="容差 (%)" value={result.tolerance_pct} precision={3} />
              <Statistic title="样本数" value={result.sample_count} />
            </Space>
          </div>
        )}
      </Card>

      <Card title="上游日报批量导入（Excel）">
        <Upload.Dragger
          accept=".xlsx,.xlsm"
          beforeUpload={onUpload}
          showUploadList={false}
          disabled={uploading}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽文件上传</p>
          <p className="ant-upload-hint">支持 4 列：业务日期 / 气源代码 / 上游计量Nm³ / 备注。首行为表头时会自动识别。</p>
        </Upload.Dragger>

        {uploadResult && (
          <Table
            rowKey="row_index"
            style={{ marginTop: 16 }}
            size="small"
            pagination={false}
            dataSource={uploadResult.rows}
            columns={[
              { title: "行号", dataIndex: "row_index", width: 70 },
              { title: "业务日期", dataIndex: "business_date", width: 110 },
              { title: "气源", dataIndex: "source_code", width: 100 },
              { title: "厂内(Nm³)", dataIndex: "plant_volume_nm3", render: (v) => v?.toLocaleString() ?? "-" },
              { title: "上游(Nm³)", dataIndex: "upstream_volume_nm3", render: (v) => v?.toLocaleString() ?? "-" },
              { title: "相对偏差(%)", dataIndex: "relative_diff_pct", render: (v) => v?.toFixed(3) ?? "-" },
              {
                title: "判定",
                dataIndex: "verdict",
                width: 100,
                render: (v) => (v ? <Tag color={VERDICT_COLOR[v]}>{v}</Tag> : "-"),
              },
              { title: "错误", dataIndex: "error", render: (v) => v ? <span style={{ color: "#cf1322" }}>{v}</span> : "-" },
            ]}
          />
        )}
      </Card>
    </Space>
  );
}
