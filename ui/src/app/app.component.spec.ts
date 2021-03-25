import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ReactiveFormsModule } from '@angular/forms';
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import { By } from '@angular/platform-browser';

import { MatToolbarModule } from '@angular/material/toolbar';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { HarnessLoader } from '@angular/cdk/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { MatButtonHarness } from '@angular/material/button/testing';
import { MatButtonToggleGroupHarness, MatButtonToggleHarness } from '@angular/material/button-toggle/testing';
import { MatSnackBarHarness } from '@angular/material/snack-bar/testing';

import { AppComponent } from './app.component';
import { ChargeMode, PvControl } from './pv-control.service';
import { HttpStatusInterceptor } from './http-status.service';


describe('AppComponent', () => {
  let loader: HarnessLoader;
  let httpMock: HttpTestingController;
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;
  let pvControlData: PvControl;
  let chargeModeOff1P: MatButtonToggleHarness;
  let chargeModeOff3P: MatButtonToggleHarness;
  let refreshButton: MatButtonHarness;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        BrowserAnimationsModule,
        HttpClientTestingModule,
        ReactiveFormsModule,
        MatToolbarModule,
        MatCardModule,
        MatFormFieldModule,
        MatInputModule,
        MatIconModule,
        MatButtonModule,
        MatButtonToggleModule,
        MatSlideToggleModule,
        MatSnackBarModule,
      ],
      declarations: [
        AppComponent
      ],
      providers: [
        {
          provide: HTTP_INTERCEPTORS,
          useClass: HttpStatusInterceptor,
          multi: true,
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    loader = TestbedHarnessEnvironment.loader(fixture);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);

    pvControlData = {
      meter: {
        power_pv: 5000,
        power_consumption: 3000,
        power_grid: 2000
      },
      wallbox: {
        allow_charging: true,
        max_current: 8,
        phases_in: 3,
        phases_out: 3,
        power: 2000,
      },
      controller: {
        mode: ChargeMode.OFF_3P,
        desired_mode: ChargeMode.OFF_3P
      }
    };

    chargeModeOff1P = await loader.getHarness(MatButtonToggleHarness.with({selector: '#chargeModeOFF_1P'}));
    chargeModeOff3P = await loader.getHarness(MatButtonToggleHarness.with({selector: '#chargeModeOFF_3P'}));
    refreshButton = await loader.getHarness(MatButtonHarness.with({selector: '#refresh'}));
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should render the app', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(component.chargeModeControl.value).toBe(ChargeMode.OFF_3P);
    expect(await chargeModeOff3P.isChecked()).toBeTrue();
  });

  it('should refresh data', async () => {
    const refreshIcon = fixture.debugElement.query(By.css('#refresh mat-icon')).nativeElement;

    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
    fixture.detectChanges();

    expect(refreshIcon.className).not.toContain('spin');
    expect(component.pvControl).toEqual(pvControlData);
    expect(component.chargeModeControl.value).toBe(ChargeMode.OFF_3P);

    pvControlData.controller.mode = ChargeMode.OFF_1P;
    pvControlData.controller.desired_mode = ChargeMode.OFF_1P;
    await refreshButton.click();

    expect(refreshIcon.className).toContain('spin');
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(component.chargeModeControl.value).toBe(ChargeMode.OFF_1P);
    expect(await chargeModeOff1P.isChecked()).toBeTrue();
    expect(refreshIcon.className).not.toContain('spin');
  });

  it('should show an error msg on http problems', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    await refreshButton.click();
    httpMock.expectOne('./api/pvcontrol').flush('', {
      status: 500,
      statusText: 'Internal Server Error'
    });

    // snack bar is not below root element of fixture -> can't use loader
    const snackbar = await TestbedHarnessEnvironment.documentRootLoader(fixture).getHarness(MatSnackBarHarness);
    expect(await snackbar.getMessage()).toBe('HTTP 500 Internal Server Error - GET ./api/pvcontrol');
  });

  it('should allow to switch to one phase charging', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    await chargeModeOff1P.check();

    const req = httpMock.expectOne('./api/pvcontrol/controller/desired_mode');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe('"OFF_1P"');
    req.flush(null);

    expect(await chargeModeOff1P.isChecked()).toBeTrue();
    expect(await chargeModeOff3P.isChecked()).toBeFalse();
  });
});
