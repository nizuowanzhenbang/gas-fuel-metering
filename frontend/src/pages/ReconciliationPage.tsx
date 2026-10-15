import { useEffect, useState } from "react";
import { Alert, Button, Card, DatePicker, Form, InputNumber, Select, Space, Statistic, Table, Tag, Upload, message } from "antd";
import { InboxOutlined, ThunderboltOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { isAxiosError } from "axios";
import {
  DailyReconResult,
  BusinessPolicy, getBusinessPolicy,
  MeteringEvidence,
  GasSource,
  UploadResponse,
  listGasSources,
  reconcileDaily,
  uploadUpstreamDaily,
} from "../api/resources";

const VERDICT_COLOR: Record<string, string> = { PASS: "green", WARN: "orange", FAIL: "red" };
const ISSUE_LABEL: Record<string, string> = {
  INSUFFICIENT_SAMPLES: "有效读数不足两条", INCOMPLETE_DAY: "缺少完整日边界",
  COUNTER_ROLLBACK: "累计表回退，需核对复位", DUPLICATE_TIMESTAMP: "同一时刻存在多条读数",
  INVALID_COUNTER: "累计值无效", MISALIGNED_LOOPS: "主备计量区间不一致",
};

export default function ReconciliationPage() {
  const [policy, setPolicy] = useState<BusinessPolicy | null>(null);
  const [sources, setSources] = useState<GasSource[]>([]);
  const [result, setResult] = useState<DailyReconResult | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [form] = Form.useForm();
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [qualityError, setQualityError] = useState<{ message: string; stations: MeteringEvidence[] } | null>(null);

  useEffect(() => {
    listGasSources({ size: 200 }).then((r) => setSources(r.items));
    getBusinessPolicy().then(p => { setPolicy(p); form.setFieldsValue({ business_date: dayjs(p.latest_completed_date) }); });
  }, []);

  const onRun = async () => {
    const v = await form.validateFields();
    setResult(null);
    setQualityError(null);
    setRunning(true);
    try {
      const r = await reconcileDaily({
        source_id: v.source_id,
        business_date: v.business_date.format("YYYY-MM-DD"),
        upstream_volume_nm3: v.upstream_volume_nm3,
      });
      setResult(r);
    } catch (error) {
      if (isAxiosError(error) && error.response?.data?.detail?.code === "METERING_DATA_QUALITY") {
        setQualityError(error.response.data.detail);
      }
    } finally {
      setRunning(false);
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
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message={policy ? `业务口径 ${policy.timezone}，日切 ${String(Math.floor(policy.start_minute / 60)).padStart(2,"0")}:${String(policy.start_minute % 60).padStart(2,"0")}。日期指区间起始日；每站需完整首末累计读数。` : "业务口径加载中"} />
        <Form form={form} layout="inline" onFinish={onRun} >
          <Form.Item name="source_id" label="气源" rules={[{ required: true }]}>
            <Select style={{ width: 240 }} options={sources.map((s) => ({ value: s.id, label: `${s.code} ${s.name}` }))} />
          </Form.Item>
          <Form.Item name="business_date" label="业务日期" rules={[{ required: true }]}>
            <DatePicker />
          </Form.Item>
          <Form.Item name="upstream_volume_nm3" label="上游计量(Nm³)" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: 180 }} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={running} disabled={!policy}>执行对账</Button>
        </Form>

        {result && (
          <div style={{ marginTop: 16 }}>
            <Alert
              type={result.verdict === "PASS" ? "success" : result.verdict === "WARN" ? "warning" : "error"}
              showIcon
              message={
                <span>
                  {result.source_code} / {result.business_date} ({result.window.policy.timezone}) 对账判定 <Tag color={VERDICT_COLOR[result.verdict]}>{result.verdict}</Tag> — {result.reason}
                </span>
              }
            />
            <p>业务区间 UTC：{result.window.start_utc} → {result.window.end_utc}</p>
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
        {qualityError && <Alert type="warning" showIcon style={{ marginTop: 16 }}
          message="数据待核对，未生成对账结论" description="请核对下方站点与读数；修正数据后重新执行。" />}
        {(result || qualityError) && <Table<MeteringEvidence>
          style={{ marginTop: 16 }} size="small" pagination={false} scroll={{ x: 1000 }}
          rowKey={(row) => `${row.station_id}-${row.source}`}
          dataSource={qualityError?.stations ?? result?.stations ?? []}
          columns={[
            { title: "站点 ID", dataIndex: "station_id" },
            { title: "回路", dataIndex: "source" },
            { title: "起始 (UTC)", dataIndex: "first_ts", render: (v) => v || "缺失" },
            { title: "结束 (UTC)", dataIndex: "last_ts", render: (v) => v || "缺失" },
            { title: "有效/排除", render: (_, r) => `${r.sample_count} / ${r.excluded_count}` },
            { title: "首值", dataIndex: "start_counter_nm3", render: (v) => v ?? "—" },
            { title: "末值", dataIndex: "end_counter_nm3", render: (v) => v ?? "—" },
            { title: "计量 (Nm³)", dataIndex: "volume_nm3", render: (v) => v ?? "未计算" },
            { title: "数据检查", render: (_, r) => r.issues.length
              ? r.issues.map(issue => <Tag color="orange" key={issue}>{ISSUE_LABEL[issue] || issue}</Tag>)
              : <Tag color="green">通过</Tag> },
          ]}
        />}
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
            expandable={{
              rowExpandable: (row) => row.stations.length > 0,
              expandedRowRender: (row) => <Table<MeteringEvidence> size="small" pagination={false}
                rowKey={(e) => `${e.station_id}-${e.source}`} dataSource={row.stations} scroll={{ x: 900 }}
                columns={[
                  { title: "站点 ID", dataIndex: "station_id" },
                  { title: "回路", dataIndex: "source" },
                  { title: "起始 UTC", dataIndex: "first_ts", render: (v) => v || "缺失" },
                  { title: "结束 UTC", dataIndex: "last_ts", render: (v) => v || "缺失" },
                  { title: "有效/排除", render: (_, r) => `${r.sample_count} / ${r.excluded_count}` },
                  { title: "首值", dataIndex: "start_counter_nm3", render: (v) => v ?? "—" },
                  { title: "末值", dataIndex: "end_counter_nm3", render: (v) => v ?? "—" },
                  { title: "计量 Nm³", dataIndex: "volume_nm3", render: (v) => v ?? "未计算" },
                  { title: "数据检查", render: (_, r) => r.issues.length
                    ? r.issues.map(issue => ISSUE_LABEL[issue] || issue).join("；") : "通过" },
                ]} />,
            }}
            columns={[
              { title: "行号", dataIndex: "row_index", width: 70 },
              { title: "业务日期", dataIndex: "business_date", width: 110 },
              { title: "业务区间 UTC", render: (_, row) => row.window ? `${row.window.start_utc} → ${row.window.end_utc}` : "—" },
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
